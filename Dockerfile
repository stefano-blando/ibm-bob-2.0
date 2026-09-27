# Flight Recorder demo (Hugging Face Space / any container host).
# Serves the dashboard; its "Run scripted rogue agent" button runs the deterministic scenario
# (real hook handler + inotify layer) on a throwaway copy. No Bob, no API keys needed.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
COPY --chown=user . .
RUN pip install --no-cache-dir --user -e backend \
 && git init -q && git add -A && git -c user.email=demo@nagare -c user.name=demo commit -qm snapshot
ENV PATH="/home/user/.local/bin:${PATH}"
EXPOSE 7860
CMD ["nagare", "ui", "--repo", ".", "--host", "0.0.0.0", "--port", "7860"]
