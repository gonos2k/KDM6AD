# S2 dry-number selector at the v2 C ABI

The [C++ core](REPORT_S2_cpp_dry_number_2026-09-28.md) has an opt-in
dry-specific QN path, but existing C ABI calls still select the legacy raw
number path. The v2 forward options struct now appends a separate
`dry_number` field. Absent or zero keeps the existing calculation; one selects
the C++ dry-number path for a value-only call. Other values and a dry-number
AD request fail before tensor work or output writes. The v1 forward and both
existing fp64 AD entry signatures are unchanged.

The field is `int64_t`, matching Fortran `integer(c_int64_t)` despite carrying
only 0/1. On the local 64-bit ABI,
the old struct is 336 bytes and ends with four bytes of padding after
`physics_variant`; a `uint32_t` addition would fit in that padding and leave
the size unchanged. The 64-bit field begins at offset 336 and grows the
struct to 344 bytes. This keeps the Fortran `c_sizeof` mirror check useful:
an old 336-byte mirror cannot claim the new 344-byte layout. An older C v2
caller that correctly reports its own 336-byte `struct_size` remains valid,
and the library does not read the absent tail.

The public ISO_C_BINDING mirror appends the matching `integer(c_int64_t)` and
sets the selector explicitly to zero in its existing forward smoke. Focused
C ABI tests cover the old and one-byte-short struct sizes, explicit zero,
active one, unknown positive and negative values, untouched outputs and null
handle on rejection, and value-only restriction. The isolated macOS build and
the focused `c_abi`, `fortran_smoke` and `fortran_normalized_ad` CTests passed.

This does not update the private mp137 host caller or its private ISO mirror.
Any private v2 caller recompiled with the enlarged mirror must explicitly set
`dry_number=0` until it selects the dry-specific path; advertising the new
`c_sizeof` while leaving the field undefined would be invalid. Old compiled
callers with their original smaller `struct_size` continue to default to zero.
The host's first-step CCN profile is still initialized as a volume number and
must be converted once before an opt-in dry-specific ABI call. The fp64 AD ABI
does not expose this selector; no native mp137 trajectory, host diagnostic
conversion, physical threshold calibration or observation acceptance is
claimed. S2 and default-path approval remain OPEN. No deployment action is
part of this change.
