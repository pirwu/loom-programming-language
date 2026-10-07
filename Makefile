CC      ?= gcc
CFLAGS  ?= -std=c11 -O2 -Wall -Wextra -Wno-unused-parameter -D_DEFAULT_SOURCE -D_GNU_SOURCE
LDFLAGS ?= -lm

SRC_DIR := src/loom
BUILD   := build
BIN     := $(BUILD)/loom

SRCS := $(SRC_DIR)/value.c $(SRC_DIR)/lexer.c $(SRC_DIR)/parser.c \
        $(SRC_DIR)/interp.c $(SRC_DIR)/stdlib.c $(SRC_DIR)/main.c
OBJS := $(SRCS:$(SRC_DIR)/%.c=$(BUILD)/%.o)

.PHONY: all clean test demo

all: $(BIN)

$(BIN): $(OBJS)
	@mkdir -p $(BUILD)
	$(CC) $(OBJS) -o $@ $(LDFLAGS)

$(BUILD)/%.o: $(SRC_DIR)/%.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -I$(SRC_DIR) -c $< -o $@

test: $(BIN)
	@bash tests/run_tests.sh

demo: $(BIN)
	$(BIN) examples/hello.loom
	$(BIN) examples/fizzbuzz.loom
	$(BIN) examples/functions.loom
	$(BIN) examples/classes.loom
	$(BIN) examples/files.loom

clean:
	rm -rf $(BUILD)
