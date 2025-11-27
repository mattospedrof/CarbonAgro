# backend/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import rasterio
import numpy as np
from rasterio.io import MemoryFile
import json
from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm

app = FastAPI(title="CarbonAgro API - NDVI service (PNG & GeoTIFF)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "CarbonAgro API - NDVI service (GeoTIFF + PNG preview)"}

@app.post("/upload-geojson")
async def upload_geojson(file: UploadFile = File(...)):
    contents = await file.read()
    try:
        geo = json.loads(contents)
        features = geo.get("features", [])
        try:
            import geopandas as gpd
            bbox = gpd.GeoDataFrame.from_features(features).total_bounds.tolist()
        except Exception:
            bbox = []
        return {"features": len(features), "bbox": bbox}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

def compute_ndvi_array(red_arr, nir_arr, fill_value=-9999.0):
    """Compute NDVI array and set invalids to fill_value."""
    red = red_arr.astype('float32')
    nir = nir_arr.astype('float32')
    np.seterr(divide='ignore', invalid='ignore')
    ndvi = (nir - red) / (nir + red)
    ndvi = np.where(np.isfinite(ndvi), ndvi, fill_value).astype('float32')
    return ndvi

@app.post("/compute-ndvi")
async def compute_ndvi(red: UploadFile = File(...), nir: UploadFile = File(...)):
    """
    Recebe dois GeoTIFFs (red e nir) e retorna um GeoTIFF com NDVI.
    Output: application/octet-stream (ndvi.tif)
    """
    try:
        red_bytes = await red.read()
        nir_bytes = await nir.read()
        with MemoryFile(red_bytes) as red_mem, MemoryFile(nir_bytes) as nir_mem:
            with red_mem.open() as red_src, nir_mem.open() as nir_src:
                if red_src.width != nir_src.width or red_src.height != nir_src.height:
                    raise HTTPException(status_code=400, detail="Red and NIR rasters must have same dimensions")
                red_arr = red_src.read(1)
                nir_arr = nir_src.read(1)
                ndvi = compute_ndvi_array(red_arr, nir_arr)
                profile = red_src.profile
                profile.update(dtype=rasterio.float32, count=1, compress='lzw', nodata=-9999.0)

                out_mem = MemoryFile()
                with out_mem.open(**profile) as dst:
                    dst.write(ndvi, 1)
                out_mem.seek(0)
                data = out_mem.read()
                headers = {
                    "Content-Disposition": 'attachment; filename="ndvi.tif"',
                    "Content-Type": "application/octet-stream"
                }
                return Response(content=data, media_type="application/octet-stream", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compute-ndvi-png")
async def compute_ndvi_png(red: UploadFile = File(...), nir: UploadFile = File(...)):
    """
    Recebe dois GeoTIFFs (red e nir) e retorna uma imagem PNG colorizada do NDVI
    (boa para preview e inclusão em artigos). Também retorna, via header,
    estatísticas resumo do NDVI (mean, std, min, max).
    Output: image/png
    """
    try:
        red_bytes = await red.read()
        nir_bytes = await nir.read()
        with MemoryFile(red_bytes) as red_mem, MemoryFile(nir_bytes) as nir_mem:
            with red_mem.open() as red_src, nir_mem.open() as nir_src:
                if red_src.width != nir_src.width or red_src.height != nir_src.height:
                    raise HTTPException(status_code=400, detail="Red and NIR rasters must have same dimensions")
                red_arr = red_src.read(1)
                nir_arr = nir_src.read(1)
                ndvi = compute_ndvi_array(red_arr, nir_arr, fill_value=np.nan)  # use nan for plotting

                # Stats (ignore nan)
                valid = np.isfinite(ndvi)
                if np.any(valid):
                    mean_ndvi = float(np.nanmean(ndvi))
                    std_ndvi = float(np.nanstd(ndvi))
                    min_ndvi = float(np.nanmin(ndvi))
                    max_ndvi = float(np.nanmax(ndvi))
                else:
                    mean_ndvi = std_ndvi = min_ndvi = max_ndvi = 0.0

                # Create PNG figure (no axes, paper-ready)
                fig = plt.figure(figsize=(6, 6), dpi=200)
                ax = fig.add_axes([0,0,1,1])
                ax.set_axis_off()
                # Choose a perceptually-uniform colormap suitable for NDVI
                cmap = cm.get_cmap('RdYlGn')  # diverging, green = high
                # Clip NDVI to [-1, 1] for visualization
                ndvi_vis = np.clip(ndvi, -1.0, 1.0)
                im = ax.imshow(ndvi_vis, cmap=cmap, vmin=-1, vmax=1)
                # Add small colorbar to the right (for articles)
                cax = fig.add_axes([0.92, 0.05, 0.02, 0.9])
                plt.colorbar(im, cax=cax, format="%.2f")
                buf = BytesIO()
                plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.01)
                plt.close(fig)
                buf.seek(0)
                headers = {
                    "X-NDVI-MEAN": str(mean_ndvi),
                    "X-NDVI-STD": str(std_ndvi),
                    "X-NDVI-MIN": str(min_ndvi),
                    "X-NDVI-MAX": str(max_ndvi),
                    "Content-Disposition": 'inline; filename="ndvi_preview.png"'
                }
                return Response(content=buf.getvalue(), media_type="image/png", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
