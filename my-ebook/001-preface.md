# Preface

This book is another of those books I wanted to read but did not exist.

When I started writing idiomatic C++ for low-latency systems, I kept hitting the same wall: there was no single resource that explained the _why_ behind C++ idioms in a way that connected the dots. Individual idioms were documented in blog posts, conference talks, and standards proposals, but nobody had laid them out end-to-end — from RAII and value semantics all the way to expression templates, coroutines, and compile-time reflection — with a consistent philosophy and a focus on real-world trade-offs rather than textbook examples.

This book tries to fill that gap. It covers over 60 idioms across 33 chapters and 14 parts, organized so that each idiom builds on concepts introduced earlier. The journey starts with foundational ideas (RAII, value semantics, move semantics) and moves through memory management, polymorphism techniques, functional patterns, concurrency, template metaprogramming, error handling, performance optimization, and design patterns adapted to C++'s unique strengths. The later chapters tackle advanced topics — mixin-based design, expression templates, variadic patterns, and the newly emerging world of C++26 static reflection.

Every code snippet in this book is preceded by an explanation of _why_ it exists and followed by a discussion of its consequences, limits, and alternatives. My goal is not to give you a catalogue of tricks, but to build a mental model of how C++ idioms work together — how RAII shapes ownership, how type erasure enables runtime polymorphism without inheritance, how expression templates fuse loops at compile time, and how all of these ideas reinforce each other when you understand the underlying principles.

The book is aimed at intermediate-to-experienced C++ programmers who already know the syntax but want to write code that is idiomatic, maintainable, and efficient. If you are building low-latency trading systems, game engines, embedded software, databases, or any performance-sensitive application in C++, the patterns here should serve as a practical reference.

I have tried to make the content as clear and accurate as possible, but no technical book of this scope is error-free. If you find mistakes, unclear explanations, or topics you would like to see covered, please reach out to jissbooks@gmail.com. I will correct errors and update the book.

Rainer Sanchez Navarro
