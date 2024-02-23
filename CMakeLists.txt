cmake_minimum_required(VERSION 3.15)

set(library_name _peripherals)

file(GLOB_RECURSE sources *.h)

add_bsp_based_library(NAME ${library_name} SOURCES ${sources})
target_include_directories(${library_name} PUBLIC .)
target_compile_options(${library_name} PRIVATE -O0)