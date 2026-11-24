#!/usr/bin/env python3
"""Per-symbol report for the guest PC histogram written by `ZEEBX_PCSAMPLE`.

`ZEEBX_PCSAMPLE=N` makes the emulator stop the guest every N instructions and count the PC, and
`ZEEBX_PCSAMPLE_OUT=file` writes `pc lr saved count` lines (hex, four columns). This script turns
that file into a profile: each sample is attributed to the function that contains the PC, and the
result is the percentage of samples per function, in descending order.

The symbols come from the ELF the game was built into:

    python3 tools/pcsample_report.py profile.txt --elf build/sa1g.elf
    python3 tools/pcsample_report.py profile.txt --nm syms.txt --base 0x10200 --top 30

`--nm` takes the output of `arm-none-eabi-nm -n` (address and name per line) for when there is no
ELF at hand. `--base` is subtracted from every PC first: an applet loaded by the module loader is
not linked at the address it runs from, and the offset is the difference between the two.

A sample that lands on a float helper is attributed to the caller (`lr`, or the saved word when
the caller is itself a helper): on the Zeebo the hardware float unit does not exist and the
soft-float calls dominate the profile, hiding the game code that asked for them. `--no-flatten`
counts them where they are.
"""

import argparse
import bisect
import collections
import subprocess
import sys

# The ARM soft-float and libgcc helpers that only exist because the Zeebo's ARM11 has no VFP.
# A sample here is reported against the caller, and they are summed as "soft-float".
SOFT_FLOAT = {
    "__aeabi_fadd", "__aeabi_fsub", "__aeabi_fmul", "__aeabi_fdiv", "__aeabi_frsub",
    "__aeabi_fcmpeq", "__aeabi_fcmplt", "__aeabi_fcmple", "__aeabi_fcmpge", "__aeabi_fcmpgt",
    "__aeabi_cfcmpeq", "__aeabi_cfcmple", "__aeabi_cfcmplt", "__aeabi_cfrcmple",
    "__addsf3", "__subsf3", "__mulsf3", "__divsf3", "__negsf2", "__cmpsf2",
    "__eqsf2", "__nesf2", "__ltsf2", "__lesf2", "__gtsf2", "__gesf2",
    "__floatsisf", "__floatdisf", "__floatunsisf", "__fixsfsi", "__fixunssfsi",
}
# The comparison wrappers: when the caller is one of these, the interesting frame is one above.
WRAPPERS = {
    "__aeabi_cfcmpeq", "__aeabi_cfcmple", "__aeabi_cfcmplt", "__aeabi_cfrcmple",
    "__aeabi_fcmpeq", "__aeabi_fcmple", "__aeabi_fcmplt", "__aeabi_fcmpge", "__aeabi_fcmpgt",
}


def load_symbols(path, elf):
    """`[(address, name)]`, ordered, from the ELF or from an `nm -n` listing."""
    if elf:
        out = subprocess.run(
            ["arm-none-eabi-nm", "-n", "--defined-only", elf],
            capture_output=True, text=True, check=True,
        ).stdout
        lines = out.splitlines()
    else:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    symbols = []
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        # `nm` prints "00001cbc T name" and, without `-n`, "00001cbc T name" as well; a
        # hand-trimmed listing of "address name" is accepted too.
        if len(parts) >= 3:
            address, name = parts[0], parts[2]
        else:
            address, name = parts[0], parts[1]
        try:
            symbols.append((int(address, 16), name))
        except ValueError:
            continue
    symbols.sort()
    return symbols


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("samples", help="the file written by ZEEBX_PCSAMPLE_OUT")
    parser.add_argument("--elf", help="the ELF the symbols come from")
    parser.add_argument("--nm", help="an `arm-none-eabi-nm -n` listing, when there is no ELF")
    parser.add_argument("--base", type=lambda v: int(v, 0), default=0,
                        help="subtracted from every PC before the lookup (load offset)")
    parser.add_argument("--top", type=int, default=25, help="how many lines to print")
    parser.add_argument("--no-flatten", action="store_true",
                        help="count the soft-float helpers where they are")
    args = parser.parse_args()
    if not args.elf and not args.nm:
        parser.error("one of --elf or --nm is required")

    symbols = load_symbols(args.nm, args.elf)
    if not symbols:
        sys.exit("no symbols")
    addresses = [address for address, _ in symbols]

    def name_of(address):
        address -= args.base
        index = bisect.bisect_right(addresses, address) - 1
        if index < 0:
            return "?"
        return symbols[index][1]

    samples = []
    with open(args.samples, encoding="utf-8") as handle:
        for line in handle:
            fields = line.split()
            if len(fields) != 4:
                continue
            try:
                pc, lr, saved, count = (int(field, 16) for field in fields)
            except ValueError:
                continue
            samples.append((pc, lr, saved, count))
    total = sum(count for *_, count in samples)
    if not total:
        sys.exit("no samples")

    counted = collections.Counter()
    soft = 0
    for pc, lr, saved, count in samples:
        name = name_of(pc)
        if not args.no_flatten and name in SOFT_FLOAT:
            caller = name_of(lr)
            if caller in WRAPPERS:
                caller = name_of(saved)
            counted[caller] += count
            soft += count
        else:
            counted[name] += count

    print(f"amostras {total}  soft-float {100 * soft / total:.1f}%")
    for name, count in counted.most_common(args.top):
        print(f"{100 * count / total:5.1f}%  {name}")


if __name__ == "__main__":
    main()
