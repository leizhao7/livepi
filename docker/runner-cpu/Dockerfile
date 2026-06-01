FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/livepi

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    curl \
    git \
    iptables \
    iproute2 \
    jq \
    nodejs \
    npm \
    openssh-client \
    procps \
    rsync \
    sudo \
    tini \
    ufw \
    unattended-upgrades \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/livepi
COPY pyproject.toml README.md ./
COPY src ./src
COPY prompt_injection_lab ./prompt_injection_lab
COPY scripts ./scripts
COPY clear_openclaw_history.py create_remote_user_folder.py setup_openclaw_benchmark_env.py ./
COPY secrets.example.env CITATION.cff DATASET_CARD.md LICENSE LICENSE-DATA ./

RUN cd prompt_injection_lab/fixtures/skills/imap-smtp-email \
  && npm install --omit=dev \
  && npm cache clean --force
RUN pip install -r prompt_injection_lab/fixtures/skills/solana/requirements.txt
RUN pip install -U pip setuptools wheel && pip install -e .
RUN npm install -g @openai/codex @anthropic-ai/claude-code \
  && npm cache clean --force

ARG INSTALL_HERMES=false
ARG HERMES_INSTALL_BRANCH=main
ARG HERMES_INSTALL_URL=https://raw.githubusercontent.com/NousResearch/hermes-agent/${HERMES_INSTALL_BRANCH}/scripts/install.sh
RUN if [ "${INSTALL_HERMES}" = "true" ]; then \
      curl -fsSL "${HERMES_INSTALL_URL}" | bash -s -- --skip-setup --skip-browser --dir /opt/hermes-agent --hermes-home /root/.hermes; \
    fi

# Hermes installer drops the launcher in /root/.local/bin which is not in
# the slim image's default PATH. Make it discoverable so adapters that
# call "hermes ..." work without absolute paths.
ENV PATH=/root/.local/bin:${PATH}

RUN mkdir -p /workspace /root/.ssh
WORKDIR /workspace

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash"]
