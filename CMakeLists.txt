cmake_minimum_required(VERSION 3.20)
project(pokemon_pvs LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

add_library(pokemon_pvs SHARED cpp/src/engine.cpp)
target_include_directories(pokemon_pvs PRIVATE cpp/include)
target_compile_definitions(pokemon_pvs PRIVATE PVS_BUILDING_DLL=1)
if(MSVC)
  target_compile_options(pokemon_pvs PRIVATE /O2 /GL /arch:AVX2 /EHsc)
  target_link_options(pokemon_pvs PRIVATE /LTCG)
else()
  # The search uses NaN as an explicit "not evaluated" sentinel.
  # -ffast-math assumes NaNs do not exist and can invalidate isfinite checks.
  target_compile_options(pokemon_pvs PRIVATE -O3 -DNDEBUG -fvisibility=hidden)
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
    target_compile_options(pokemon_pvs PRIVATE -mavx2)
  endif()
  target_link_libraries(pokemon_pvs PRIVATE dl pthread)
endif()

install(TARGETS pokemon_pvs LIBRARY DESTINATION . RUNTIME DESTINATION .)
