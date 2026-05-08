#!/bin/ksh


module purge

module load prg_env/intel_2021.3
#module load intel/20.4
#module load impi/2021.3.0
#module load mpich/3.3.2
#module load lapack/3.5.0
#module load blas/3.5.0

module load netcdfpack/4.7.3
module load pnetcdf/1.12.1
module load hdf5/1.10.3
module load hdf5-parallel/1.10.3
module load jasper/1.900.1
module load ncl/6.6.2_v2
module load imagemagick

export NETCDF=/opt/kma/kma_lib/apps/netcdfpack/4.7.3/INTEL/200
export PNETCDF=/opt/kma/kma_lib/apps/pnetcdf/1.12.1/INTEL/200
export HDF5=/opt/kma/kma_lib/apps/hdf5/1.10.3/INTEL/200
export PHDF5=/opt/kma/kma_lib/apps/hdf5-parallel/1.10.3/INTEL/200
export JASPERLIB=/opt/kma/kma_lib/apps/jasper/1.900.1/lib
export JASPERINC=/opt/kma/kma_lib/apps/jasper/1.900.1/include
export NCARG_ROOT=/opt/kma/kma_lib/apps/ncl/6.6.2/INTEL/200_png16
export WRFIO_NCD_LARGE_FILE_SUPPORT=1
#export RIP_ROOT=/h3/home/nimr/yhlee/RIP_47

echo ''
echo '***** Env for WRF '
if [ -n "$NETCDF" ] ; then
    echo '   NETCDF    = '$NETCDF
fi
if [ -n "$PNETCDF" ] ; then
    echo '   PNETCDF   = '$PNETCDF
fi
if [ -n "$HDF5" ] ; then
    echo '   HDF5      = '$HDF5
fi
if [ -n "$PHDF5" ] ; then
    echo '   PHDF5     = '$PHDF5
fi
if [ -n "$JASPERLIB" ] ; then
    echo '   JASPERLIB = '$JASPERLIB
fi
if [ -n "$JASPERINC" ] ; then
    echo '   JASPERINC = '$JASPERINC
fi
if [ -n "$WRFIO_NCD_NO_LARGE_FILE_SUPPORT" ] ; then
    echo '   WRFIO_NCD_NO_LARGE_FILE_SUPPORT = '$WRFIO_NCD_NO_LARGE_FILE_SUPPORT
fi
echo ''
