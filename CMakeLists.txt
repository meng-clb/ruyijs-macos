cmake_minimum_required(VERSION 3.24)
project(ruyijs LANGUAGES C CXX)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
  message(FATAL_ERROR "CMakeLists.txt builds the Linux runtime; Windows and macOS use tools/build.py")
endif()
set(RUYIJS_DONOR_OBJ "$ENV{RUYIJS_DONOR_OBJ}" CACHE PATH "Configured Linux SpiderMonkey objdir")
if(NOT EXISTS "${RUYIJS_DONOR_OBJ}/config.status.json")
  message(FATAL_ERROR "Set RUYIJS_DONOR_OBJ to a configured Linux SpiderMonkey build")
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
find_package(PkgConfig REQUIRED)
# Linux replaces the DirectWrite/Core Text fonts, CNG/CommonCrypto and the
# WIC/ImageIO codecs with these libraries (tools/product_sources.py LINUX_ONLY).
pkg_check_modules(NATIVE REQUIRED IMPORTED_TARGET harfbuzz fontconfig openssl zlib libwebpdemux lcms2)
set(GENERATED "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(GLOB RUYIJS_SOURCE_INPUTS CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/src/*/*.cpp")
file(GLOB RUYIJS_GENERATED_INPUTS CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/tools/generated/*.h")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${PROJECT_SOURCE_DIR}/src/runtime/codec.js"
  "${PROJECT_SOURCE_DIR}/tools/generate.py"
  "${PROJECT_SOURCE_DIR}/tools/prepare_linux.py"
  "${PROJECT_SOURCE_DIR}/tools/prepare_skia_linux.py"
  "${PROJECT_SOURCE_DIR}/tools/product_sources.py"
  "${PROJECT_SOURCE_DIR}/tools/sanitizer_data.py"
  "${PROJECT_SOURCE_DIR}/profiles/firefox-environment.json"
  "${RUYIJS_DONOR_OBJ}/config.status.json"
  ${RUYIJS_GENERATED_INPUTS})
execute_process(COMMAND "${Python3_EXECUTABLE}" -B "${PROJECT_SOURCE_DIR}/tools/prepare_linux.py"
  --donor-obj "${RUYIJS_DONOR_OBJ}" --output "${GENERATED}" COMMAND_ERROR_IS_FATAL ANY)
include("${GENERATED}/sources.cmake")
# AVIF (libavif, dav1d, libyuv) and Brotli: the frozen vendor/ sources that
# tools/image_native.py and tools/compression_native.py compile on Windows and
# macOS, with the flags tools/native.py compile_foreign gives them there (-O2,
# C11/C++17, asserts on). tools/build_linux.py builds zlib-rs the same way.
include("${GENERATED}/foreign.cmake")
function(ruyijs_foreign_library name)
  set(objects)
  foreach(target IN LISTS ${name}_TARGETS)
    target_compile_options(${target} PRIVATE -O2 -UNDEBUG
      $<$<COMPILE_LANGUAGE:C>:-std=c11> $<$<COMPILE_LANGUAGE:CXX>:-std=c++17>)
    list(APPEND objects $<TARGET_OBJECTS:${target}>)
  endforeach()
  add_library(${name} STATIC ${objects})
endfunction()
ruyijs_foreign_library(ruyijs_image_native)
ruyijs_foreign_library(ruyijs_cs_brotli)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${DONOR_SOURCE}/gfx/skia/moz.build")
# Firefox's own Skia (gfx/skia of the donor's source tree), the raster backend
# Windows and macOS take from a Firefox browser build, compiled here with
# Skia's Fontconfig/FreeType ports (tools/prepare_skia_linux.py).
pkg_check_modules(SKIA_DEPS REQUIRED IMPORTED_TARGET freetype2 harfbuzz-subset fontconfig zlib)
execute_process(COMMAND "${Python3_EXECUTABLE}" -B "${PROJECT_SOURCE_DIR}/tools/prepare_skia_linux.py"
  --firefox-source "${DONOR_SOURCE}" --output "${CMAKE_CURRENT_BINARY_DIR}/firefox_skia.cmake" COMMAND_ERROR_IS_FATAL ANY)
include("${CMAKE_CURRENT_BINARY_DIR}/firefox_skia.cmake")
target_include_directories(firefox_skia PRIVATE "${RUYIJS_DONOR_OBJ}/dist/include")
set(SKIA_ROOT "${DONOR_SOURCE}/gfx/skia/skia")
add_library(ruyijs_objects OBJECT ${RUYIJS_SOURCES})
target_compile_features(ruyijs_objects PRIVATE cxx_std_20)
target_include_directories(ruyijs_objects PRIVATE src "${GENERATED}"
  "${RUYIJS_DONOR_OBJ}/dist/include" "${RUYIJS_DONOR_OBJ}/js/src" "${DONOR_SOURCE}/js/src"
  "${DONOR_SOURCE}/js/src/shell" "${SKIA_ROOT}")
target_compile_definitions(ruyijs_objects PRIVATE RUYIJS_FIREFOX_SKIA MOZILLA_CLIENT MOZ_HAS_MOZGLUE EXPORT_JS_API)
target_compile_options(ruyijs_objects PRIVATE -include "${RUYIJS_DONOR_OBJ}/js/src/js-confdefs.h"
  -fno-rtti -fno-sized-deallocation -fno-aligned-new -fPIC -ffp-contract=off -Wno-deprecated-declarations)
target_link_libraries(ruyijs_objects PRIVATE PkgConfig::NATIVE firefox_skia)
target_precompile_headers(ruyijs_objects PRIVATE <jsapi.h> "${PROJECT_SOURCE_DIR}/src/runtime/web_kit.h")
set_source_files_properties("${GENERATED}/Unified_cpp_js_src_shell0.cpp" PROPERTIES SKIP_PRECOMPILE_HEADERS ON)
set_source_files_properties(${DONOR_OBJECTS} PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
add_executable(js $<TARGET_OBJECTS:ruyijs_objects> ${DONOR_OBJECTS})
# tools/rust_runtime.py writes this only for a donor whose jsrust keeps Rust's
# std private (Firefox 159 release builds); tools/build_linux.py runs it first.
set(RUYIJS_RUST_RUNTIME "${CMAKE_CURRENT_BINARY_DIR}/rust-runtime/libruyijs_rust_runtime.a")
if(NOT EXISTS "${RUYIJS_RUST_RUNTIME}")
  set(RUYIJS_RUST_RUNTIME "")
endif()
target_link_libraries(js PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/urlpattern/target/release/libruyijs_urlpattern.a"
  "${CMAKE_CURRENT_BINARY_DIR}/compression/libruyijs_cs_zlib.a"
  ${RUYIJS_RUST_RUNTIME} ${DONOR_LIBRARIES} ruyijs_image_native ruyijs_cs_brotli
  PkgConfig::NATIVE firefox_skia pthread dl m)
target_link_options(js PRIVATE ${DONOR_LINK_FLAGS})
set_target_properties(js PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${PROJECT_SOURCE_DIR}/dist"
  BUILD_RPATH "$ORIGIN")
# The C ABI client: the same POSIX sources macOS builds (tools/client.py).
add_library(ruyijs_client SHARED src/client/api.cpp src/client/transport.cpp src/client/lifecycle.cpp)
target_compile_features(ruyijs_client PRIVATE cxx_std_20)
target_compile_options(ruyijs_client PRIVATE -fvisibility=hidden)
target_link_libraries(ruyijs_client PRIVATE pthread)
set_target_properties(ruyijs_client PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${PROJECT_SOURCE_DIR}/dist")
