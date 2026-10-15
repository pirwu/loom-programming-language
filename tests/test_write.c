#include <io.h>
int main(void) {
    char buf[] = "hello from C\n";
    _write(1, buf, 13);
    return 0;
}