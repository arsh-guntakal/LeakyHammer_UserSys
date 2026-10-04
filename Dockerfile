FROM ubuntu:20.04

# The shell should be bash so sourcing will work.
SHELL ["/bin/bash", "-c"]

# `apt-get update` was failing with DNS resolution errors (e.g. "Temporary 
# failure resolving 'archive.ubuntu.com'"). Root cause: apt downloads as the 
# unprivileged `_apt` user, which lacked write access to 
# /var/lib/apt/lists/partial in this base image; the resulting sandbox 
# permission failure was misreported as a DNS error. Fix: disable apt's 
# download sandboxing, reset the lists dir, and explicitly fail the build
# on any Err/W output, since `apt-get update` exits 0 even on partial failure.
RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99no-sandbox 
RUN rm -rf /var/lib/apt/lists
RUN set -o pipefail && \
    apt-get update 2>&1 | \
    tee /tmp/apt-update.log && \
    if grep -E '^(Err:|W:)' /tmp/apt-update.log; then \
        exit 1; \
    fi

# Install packages.
ENV DEBIAN_FRONTEND=noninteractive  
RUN apt-get update && apt-get install -y \
    build-essential=12.8ubuntu1.1 \
    g++-10=10.5.0-1ubuntu1~20.04 \
    gcc-10-base:amd64=10.5.0-1ubuntu1~20.04 \
    wget=1.20.3-1ubuntu2.1 \
    curl=7.68.0-1ubuntu2.25 \
    git=1:2.25.1-1ubuntu3.14 \
    cmake=3.16.3-1ubuntu1 \
    cmake-data=3.16.3-1ubuntu1 \
    python3=3.8.2-0ubuntu2 \
    python3-dev \
    libpython3-dev:amd64=3.8.2-0ubuntu2 \
    libpython3-stdlib:amd64=3.8.2-0ubuntu2 \
    libprotobuf-dev:amd64=3.6.1.3-2ubuntu5.2 \
    protobuf-compiler=3.6.1.3-2ubuntu5.2 \
    libgoogle-perftools-dev:amd64=2.7-1ubuntu2 \
    libboost-date-time1.71.0:amd64=1.71.0-6ubuntu6 \
    libboost-dev:amd64=1.71.0.0ubuntu2 \
    libboost-filesystem1.71.0:amd64=1.71.0-6ubuntu6 \
    libboost-iostreams1.71.0:amd64=1.71.0-6ubuntu6 \
    libboost-locale1.71.0:amd64=1.71.0-6ubuntu6 \
    libboost-thread1.71.0:amd64=1.71.0-6ubuntu6 \
    libboost1.71-dev:amd64=1.71.0-6ubuntu6 \
    zlib1g \
    zlib1g-dev \
    libc-bin=2.31-0ubuntu9.18 \
    m4=1.4.18-4 \
    vim
ENV CXX=g++-10
ENV CC=gcc-10

# Install uv. 
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install project. 
WORKDIR /app/LeakyHammer_UserSys
COPY . . 
RUN uv sync --frozen

ENTRYPOINT [ "/bin/bash", "-l", "-c" ]
