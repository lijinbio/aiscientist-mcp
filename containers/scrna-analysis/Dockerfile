# Build from the workspace root after updating uv.lock.
# docker build -f containers/scrna-analysis/Dockerfile -t mcp-scrna-analysis:0.0.2 .
FROM ghcr.io/astral-sh/uv:0.13.0 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /uvx /usr/local/bin/
LABEL org.opencontainers.image.source="https://github.com/lijinbio/aiscientist-mcp" \
      org.opencontainers.image.description="Single-cell RNA analysis MCP server" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /opt/aiscientist-mcp
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
RUN uv sync --frozen --no-dev --package aiscientist-mcp-scrna-analysis --no-editable
ENV PATH="/opt/aiscientist-mcp/.venv/bin:$PATH" \
    MPLBACKEND=Agg \
    NUMBA_CACHE_DIR=/tmp/numba
RUN python -c "import scanpy, gseapy, pydeseq2, harmonypy, leidenalg; from aiscientist_mcp.scrna_analysis.server import server"
CMD ["scrna-analysis-mcp"]
