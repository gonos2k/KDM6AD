# Explicit FP64 KDM value bridge for a native full-physics forward

The current actual-departure QR candidate admits binary64 inputs. The normal
WRF ABI decodes its REAL4 fields as Float32, so linking the candidate DSO into
that route alone is insufficient. The QR admission guard remains unchanged.

Use a distinct experimental forward-only entry,
`kdm6_native_fp64_value_c`, compiled only with
`KDM6_ENABLE_NATIVE_FP64_VALUE_BRIDGE`. The existing `kdm6_step_c` body,
default 14-symbol export set, packed AD signatures and operational install are
unchanged. An isolated Fortran ISO overlay explicitly binds its forward call
to the new symbol; it is not a hidden precision change in the operational ABI.
The experimental export list contains this one additional symbol.

## Map and derivatives

For host state/forcing x32, exact widening W, existing selected FP64 kernel K,
and REAL4 writeback Q32, the value map is

```
y32 = Q32(K(W(x32)))
```

All twelve state fields and four forcing fields are widened after the normal
Fortran-layout decode. XLAND retains its original discrete REAL4 values.
The twelve output states, three surface precipitation increments and RHOG use
the normal REAL4 copy-back layout exactly once. WRF subsequently performs its
normal cleanup/finish and RK/dynamics; the bridge adds no T/Q state or tendency.
Radiation, PBL, surface and cumulus remain in the native full-host forward.

The new entry requires `value_only=1`, returns a null handle, and rejects
recorded AD. It does not differentiate quantization, provide a full-host
JVP/VJP, or change the existing FP64 AD entry. `param_grad_flags` remains zero.
Keep the established scalar/domain checks, single-thread fence and FP
environment restoration. Invalid requests leave outputs untouched before
tensor execution; outputs after an internal numerical error are discarded.

## Budget at writeback

The FP64 physical-map budget and REAL4 storage-rounding budget are separate.
At fixed dry layer mass mu, the water change introduced only by writeback is

```
R_writeback = sum(mu * (q32_out - q64_out)) + (P32_out - P64_out)
```

For finite in-range values rounded to nearest, the absolute bound is the sum
of mu times each component's half-ULP32 bound, plus the precipitation storage
bound. Include subnormal spacing; do not treat it as a relative-error bound
near zero. Overflow is invalid. This diagnostic does not certify full-host
water/energy closure: advection, boundaries, other physics, changing mass and
the existing cleanup policies remain part of the full host.

## Acceptance before the host run

- Same widened REAL4 inputs: the experimental twelve state outputs must equal
  REAL4 casts of the existing FP64 value API, bitwise.
- Independently check the forward precipitation/RHOG copy-back and non-square
  Fortran layout against a direct FP64 runtime reference.
- Existing operational entry, with no experimental binding: all sixteen
  forward outputs must retain their prior REAL4 bytes on the admitted tests.
- Reject value_only 0/2 and invalid reserved flags with null handle and
  sentinel output buffers preserved; no added AD capability is implied.
- Verify only the intended bridge object and ISO binding changed, preserve
  `-ffp-contract=off`, and pin the consistent Torch stack and actual loader.

The resulting host experiment has REAL4 storage, FP64 KDM computation and
REAL4 writeback. It is a distinct value-only mixed-precision experiment and
does not inherit an operational REAL4 parity certificate.
