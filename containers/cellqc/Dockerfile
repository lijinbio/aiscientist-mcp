# Build from the repository root. Publish and record the resulting digest before app registration.
FROM mambaorg/micromamba:2.10.0-debian12-slim
LABEL org.opencontainers.image.source="https://github.com/lijinbio/aiscientist-mcp" \
      org.opencontainers.image.description="MCP server for CellQC 0.3.6" \
      org.opencontainers.image.licenses="MIT"
# The production skill uses this same CellQC/R stack and Python 3.12. Python 3.14 breaks
# CellQC's nuclear-fraction multiprocessing step. Conda owns these analysis dependencies.
RUN micromamba install -y -n base -c conda-forge -c bioconda \
        python=3.12 cellqc=0.3.6 r-doubletfinder scanpy anndata h5py \
        mcp=2.3.0 jsonschema setuptools=84.2.1 pip \
    && micromamba clean -a -y
COPY --chown=$MAMBA_USER:$MAMBA_USER packages/common /opt/aiscientist-mcp/packages/common
COPY --chown=$MAMBA_USER:$MAMBA_USER packages/cellqc /opt/aiscientist-mcp/packages/cellqc
ARG MAMBA_DOCKERFILE_ACTIVATE=1
RUN pip install --no-deps --no-build-isolation /opt/aiscientist-mcp/packages/common \
        /opt/aiscientist-mcp/packages/cellqc \
    && cellqc --help > /dev/null \
    && python -c "from aiscientist_mcp.cellqc.settings import load_defaults; load_defaults()"
ENV PATH=/opt/conda/bin:$PATH
CMD ["cellqc-mcp"]
