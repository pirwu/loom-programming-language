#include <io.h>
#include <stdint.h>
#include <stddef.h>

int64_t loom_print_int_rt(int64_t value, int64_t fd)
{
    char buf[32];
    int i = 0;

    uint64_t u;
    int neg = 0;
    if (value < 0) {
        neg = 1;
        u = (uint64_t)(-(value + 1)) + 1u;
    } else {
        u = (uint64_t)value;
    }

    char tmp[24];
    int j = 0;
    if (u == 0) {
        tmp[j++] = '0';
    } else {
        while (u > 0) {
            tmp[j++] = (char)('0' + (u % 10));
            u /= 10;
        }
    }

    if (neg) {
        buf[i++] = '-';
    }
    while (j > 0) {
        buf[i++] = tmp[--j];
    }
    buf[i++] = '\n';

    return (int64_t)_write((int)fd, buf, (unsigned)i);
}