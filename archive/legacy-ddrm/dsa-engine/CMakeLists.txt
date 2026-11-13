cmake_minimum_required(VERSION 3.10)
project(dsa_engine)

set(CMAKE_CXX_STANDARD 17)

include_directories(include)

add_executable(dsa_engine src/main.cpp)
