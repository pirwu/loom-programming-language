#include <cstdio>
#include <cstdint>

int64_t fib(int64_t n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

int main() {
    std::printf("%lld\n", static_cast<long long>(fib(40)));
    return 0;
}