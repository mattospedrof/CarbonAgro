"""
compute_ndvi.py - minimal example to compute NDVI from NIR and Red band rasters.
Usage:
    python compute_ndvi.py red.tif nir.tif output_ndvi.tif
This script is illustrative and minimal; production pipelines should use atmospheric correction and cloud masking.
"""
import sys
import rasterio
import numpy as np

def compute_ndvi(red_path, nir_path, out_path):
    with rasterio.open(red_path) as red_src, rasterio.open(nir_path) as nir_src:
        red = red_src.read(1).astype('float32')
        nir = nir_src.read(1).astype('float32')
        np.seterr(divide='ignore', invalid='ignore')
        ndvi = (nir - red) / (nir + red)
        profile = red_src.profile
        profile.update(dtype=rasterio.float32, count=1, compress='lzw')
        with rasterio.open(out_path, 'w', **profile) as dst:
            dst.write(ndvi.astype(rasterio.float32), 1)
    print("NDVI written to", out_path)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python compute_ndvi.py red.tif nir.tif output_ndvi.tif")
    else:
        compute_ndvi(sys.argv[1], sys.argv[2], sys.argv[3])
