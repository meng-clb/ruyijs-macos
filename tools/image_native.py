"""Build frozen source-owned libavif/dav1d; portable C, no borrowed binaries."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def frozen_inputs(source):
    """SHA-256 of each vendor/image-native file, checked against manifest.json."""
    manifest=json.loads((source/'manifest.json').read_text('utf8'))
    inputs={row['path']:digest(source/row['path']) for row in manifest['files']}
    if any(inputs[row['path']]!=row['sha256'] for row in manifest['files']):
        raise ValueError('Image codec source differs from frozen manifest')
    return inputs

def portable_units(source,windows):
    """(source, object name, flags) of each portable libavif, libyuv and dav1d unit."""
    yuv=source/'libyuv'
    units=[]
    avif=source/'libavif'
    for path in sorted((avif/'src').glob('*.c')):
        if path.name.startswith('codec_') and path.name!='codec_dav1d.c':continue
        units.append((path,'avif_'+path.stem,['-DAVIF_CODEC_DAV1D=1','-DDAV1D_API=','-DAVIF_LIBYUV_ENABLED=1',
          '-I'+str(avif/'include'),'-I'+str(source/'dav1d/include'),'-I'+str(yuv/'include')]))
    yuv_inventory=(yuv/'CMakeLists.txt').read_text('utf8').split('set ( ly_common_source_files',1)[1].split(')',1)[0]
    for name in re.findall(r'\$\{ly_src_dir\}/([^\s]+\.cc)',yuv_inventory):
        units.append((yuv/'source'/name,'yuv_'+Path(name).stem,['-I'+str(yuv/'include'),'-DLIBYUV_DISABLE_X86=1','-DLIBYUV_DISABLE_NEON=1','-DLIBYUV_DISABLE_SVE=1','-DLIBYUV_DISABLE_SME=1']))
    dav=source/'dav1d'
    moz=(dav/'moz.build').read_text('utf8')
    c_units=sorted(set(re.findall(r"'../../third_party/dav1d/(src/[^']+\.c)'",moz)))
    flags=['-DDAV1D_API=','-DSTACK_ALIGNMENT=16',
           '-I'+str(dav),'-I'+str(dav/'include'),'-I'+str(dav/'src')]
    if windows:
        flags += ['-DHAVE_ALIGNED_MALLOC=1','-D_WIN32_WINNT=0x0601','-D_CRT_SECURE_NO_WARNINGS']
    units += [(dav/unit,'dav_'+Path(unit).stem,flags) for unit in c_units]
    block=moz.split('bitdepth_basenames = [',1)[1].split(']',1)[0]
    for unit in re.findall(r"'([^']+\.c)'",block):
        for bits in (8,16):units.append((dav/'src'/unit,f'dav_{bits}_{Path(unit).stem}',flags+[f'-DBITDEPTH={bits}']))
    return units

def build(native):
    source=native.root/'vendor/image-native'
    directory=native.directory/'image-native'
    directory.mkdir(parents=True,exist_ok=True)
    inputs=frozen_inputs(source)
    compiler=native.compiler()[0]
    librarian,lib_prefix=native.librarian()
    rustc=native.donor.substs['RUSTC']
    if isinstance(rustc,list):rustc=rustc[0]
    if not Path(rustc).is_file():raise RuntimeError('The configured donor rustc is required: '+rustc)
    color_source=native.root/'src/web_media/image_color.rs'
    identity={'sources':inputs,'builder':digest(__file__),'compiler':digest(compiler),
              'colorSource':digest(color_source),'rustcPath':rustc,'rustcSHA256':digest(rustc),
              'rustc':subprocess.run([rustc,'--version'],capture_output=True,text=True,check=True).stdout,
              'librarian':digest(librarian),'include':native.env.get('INCLUDE'),
              'target':native.donor.rust_target}
    signature=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    stamp=directory/'build.json'
    library=native.static_library(directory,'ruyijs_image_avif')
    color_library=native.static_library(directory,'ruyijs_image_color')
    if stamp.is_file() and library.is_file() and not native.incremental['disabled']:
        previous=json.loads(stamp.read_text('utf8'))
        if previous.get('signature')==signature and previous.get('output')==digest(library) and color_library.is_file() and previous.get('colorOutput')==digest(color_library):return [library,color_library]
    units=portable_units(source,native.donor.windows)
    def compile_one(item):
        path,name,flags=item
        output=directory/(name+native.donor.object_suffix)
        command=native.compile_foreign(path, output, flags)
        result=subprocess.run(command,cwd=directory,env=native.env,capture_output=True,text=True)
        (directory/(name+'.log')).write_text(result.stdout+result.stderr,'utf8')
        if result.returncode:raise RuntimeError(name+': '+(result.stdout+result.stderr)[-9000:])
        return output,command
    with ThreadPoolExecutor(max_workers=8) as pool:compiled=list(pool.map(compile_one,units))
    command=native.archive(library, [p for p,_ in compiled])
    result=subprocess.run(command,cwd=directory,env=native.env,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    rust_base=native.rustc_base(rustc,'2018')
    rlib=directory/'libqcms.rlib'
    color_rlib=directory/'libruyijs_image_color.rlib'
    commands=[[*rust_base,'--crate-name=qcms','--crate-type=rlib','--cfg','feature="iccv4-enabled"','--cfg','feature="cmyk"',str(source/'qcms/src/lib.rs'),'-o',str(rlib)],
       [*rust_base,'--crate-name=ruyijs_image_color','--crate-type=rlib','--extern','qcms='+str(rlib),str(color_source),'-o',str(color_rlib)],
       native.archive(color_library, [color_rlib, rlib])]
    for rust_command in commands:
        result=subprocess.run(rust_command,cwd=directory,env=native.env,capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    if any(digest(source/path)!=checksum for path,checksum in inputs.items()) or digest(color_source)!=identity['colorSource']:
        raise ValueError('Image codec sources changed while building')
    stamp.write_text(json.dumps({'signature':signature,'identity':identity,
      'commands':[c for _,c in compiled]+[command]+commands,'output':digest(library),'colorOutput':digest(color_library)},indent=2)+'\n','utf8')
    return [library,color_library]

if __name__=='__main__':
    import argparse
    from donor import Donor
    from native import Native
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor-obj',required=True)
    parser.add_argument('--toolchain-bin',required=True)
    parser.add_argument('--vs-root')
    args=parser.parse_args()
    args.no_incremental=args.reuse_objects=False
    root=Path(__file__).resolve().parents[1]
    directory=root/'artifacts/native-four/image-dependency'
    directory.mkdir(parents=True,exist_ok=True)
    print(build(Native(Donor(args.donor_obj),root,directory,args)))
