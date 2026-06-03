"""
KDM6 상수 — module_mp_kdm6.F 라인 56-186에서 직역.

소스 위치: /home/yhlee/KDM6/KIM-meso_v1.0/phys/module_mp_kdm6.F
유의: yhlee 변경 사항 (peaut: 0.55 → 0.40 등) 반영.
"""

# ─── timestep / sub-cycling ─────────────────────────────────────
DTCLDCR = 120.0  # maximum time step for minor loops

# ─── intercept parameters ───────────────────────────────────────
N0S = 2.0e6        # snow intercept
N0SMAX = 1.0e11    # max snow intercept (T = -90C unlimited)
N0G = 4.0e6        # graupel intercept — hail_opt=0(graupel) 기본 (hail_opt=1 → 4e4)

# ─── densities ──────────────────────────────────────────────────
DENR = 1000.0      # rain density (kg/m^3) — Fortran kdm6init INPUT
DENS = 100.0       # snow density (kg/m^3)
DENI = 500.0       # ice density (kg/m^3)
DENG = 500.0       # graupel default density (Park-Lim 2024 diag_rhog 사용 시 dynamic)
DEN0 = 1.28        # 표준대기 reference density (Fortran kdm6init INPUT)

# ─── DSD shape parameters (gamma) ───────────────────────────────
ALPHA = 0.12      # exponent factor for n0s temperature dependence
MUR = 1.0         # rain DSD shape param
MUS = 0.0         # snow
MUG = 0.0         # graupel
MUI = 0.0         # ice
MUC = 2.0         # cloud water (Cohard-Pinty 2000)
DMR = 3.0         # rain diameter exponent
DMS = 3.0         # snow diameter exponent
DMG = 3.0         # graupel diameter exponent
DMI = 3.0         # ice diameter exponent
DMC = 3.0         # cloud water diameter exponent

# ─── terminal velocity coefficients (a*D^b form) ────────────────
AVTR = 841.9      # rain
BVTR = 0.8
FVTR = 0.0
AVTS = 11.72      # snow
BVTS = 0.41
AVTI = 2710.0     # cloud ice (실제 도입)
BVTI = 1.0

# ─── slope parameter limits (lamda min/max for limiting) ────────
LAMDACMAX = 5.0e5
LAMDACMIN = 1.2e4   # 82 micron
LAMDARMAX = 3.5e4   # 82 micron
LAMDARMIN = 9.61e2  # 3000 micron
LAMDASMAX = 1.8e5   # 10 micron
LAMDAGMAX = 1.8e5   # graupel — hail_opt=0(graupel) 기본 (hail_opt=1 → 2e4, ProgB 내부 처리)
LAMDAIMAX = 1.82e6  # 1 micron
LAMDAIMIN = 9.08e3  # 200 micron

# ─── activation / autoconversion ────────────────────────────────
R0 = 0.8e-5
PEAUT = 0.40       # Berry-Reinhardt autoconversion efficiency
                   # (yhlee 변경: 원본 0.55 → 0.40)
XNCR = 3.0e8       # maritime CCN reference
XNCR0 = 5.0e7
XNCR1 = 5.0e8
XMYU = 1.718e-5    # dynamic viscosity (kg m^-1 s^-1)
DICON = 11.9       # cloud-ice diameter constant
DIMAX = 500.0e-6   # max cloud-ice diameter

# ─── Bigg freezing ──────────────────────────────────────────────
PFRZ1 = 100.0
PFRZ2 = 0.66

# ─── thresholds ─────────────────────────────────────────────────
QCRMIN = 1.0e-9     # minimum mixing ratio (qr, qs) — div-safety clamp floor
EPS    = 1.0e-15    # Fortran qmin=epsilon (model_constants.F:10) — GATE thresholds only
NRMIN = 1.0e-2      # minimum rain number
NRMAX = 5.0e7
NCMAX = 5.0e10

# ─── collection efficiencies (eacXY: X = collected, Y = collector) ──
EACRC = 1.0
EACIC = 1.0
EACSC = 1.0
EACGC = 1.0
EACRI = 1.0
EACIR = 1.0
EACSR = 1.0
EACGR = 1.0
EACRS = 1.0

# ─── aggregation / saturation ───────────────────────────────────
QS0 = 6.0e-4         # threshold for aggregation
SATMAX = 1.0048      # max saturation for CCN activation (continental)
ACTK = 0.6           # CCN activation parameter
ACTR = 1.5           # activated CCN drop radius
NCCN_MIN = 1.0e8     # CCN reservoir lower clamp (Fortran entry :801) — C++ constants::NCCN_MIN
NCCN_MAX = 2.0e10    # CCN reservoir upper clamp                       — C++ constants::NCCN_MAX

# ─── Long collection kernel coefficients (Cohard-Pinty 2000 / KCE 분석해) ──
NCRK1 = 3.03e3
NCRK2 = 2.59e15
ECCBRK = 1.0         # break-up efficiency

# ─── characteristic diameters (autoconversion / accretion) ──────
DI50   = 0.5e-4   # PK97 riming threshold (50 µm)
DI100  = 1.0e-4
DI125  = 1.25e-4  # ice → snow aggregation diameter (psaut)
DI150  = 1.5e-4
DI600  = 6.0e-4   # rain self-collection medium → break-up transition
DI2000 = 2.0e-3   # rain complete break-up threshold

# ─── number concentration thresholds ────────────────────────────
# review10#2 caveat: Fortran 본문은 `ncmin_land/ncmin_sea` 두 입력 스칼라를 별도로 받아
# `slmsk` (sea/land mask)에 따라 분기 사용. 우리 oracle은 단일 NCMIN으로 단순화 —
# 운영 KIM-meso wrapper에서 land/sea 값이 달라지면 warm/cold 전반 parity drift가 가능.
# 현재는 wrapper 단계에서 처리할 simplified default. 향후 prognostic ncmin tensor로 승격 가능.
NCMIN = 1.0e-2     # default minimum nc (sea/land 구분 없음 — wrapper 영역)

# ─── terminal velocity coefficients (graupel default) ──────────
AVTG = 101.0411    # graupel — Park-Lim 2024 default (rho=400 kg/m^3)
                   # ProgB_param이 rho_x에 따라 동적 진단해 덮어씀

# ─── melt heat balance factor (microphysics 외부 reuse) ─────────
F2S = 0.44
