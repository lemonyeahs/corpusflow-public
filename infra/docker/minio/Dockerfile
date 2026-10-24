# Source build of the same upstream version as the original P0-A deployment.
# No dependency on discontinued MinIO binary registries or third-party mirrors.
FROM golang:1.24.2-bookworm@sha256:79390b5e5af9ee6e7b1173ee3eac7fadf6751a545297672916b59bfa0ecf6f71 AS build
WORKDIR /src
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org
ADD --checksum=sha256:7eb30a913fea30f18069abf194e1e78e4983b558cc526911ae1c11396a9859a5 https://codeload.github.com/minio/minio/tar.gz/0d7408fc9969caf07de6a8c3a84f9fbb10a6739e /source.tar.gz
RUN tar -xzf /source.tar.gz --strip-components=1 \
    && go mod download \
    && go mod verify \
    && go build -p 2 -mod=readonly -trimpath -buildvcs=false \
       -ldflags='-s -w -X github.com/minio/minio/cmd.Version=2025-04-22T22:12:26Z -X github.com/minio/minio/cmd.ReleaseTag=DEVELOPMENT.2025-04-22T22-12-26Z -X github.com/minio/minio/cmd.CommitID=0d7408fc9969caf07de6a8c3a84f9fbb10a6739e -X github.com/minio/minio/cmd.ShortCommitID=0d7408fc9969 -X github.com/minio/minio/cmd.CopyrightYear=2025' \
       -o /out/minio . \
    && go clean -cache -modcache

FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="0d7408fc9969caf07de6a8c3a84f9fbb10a6739e" \
      org.opencontainers.image.version="RELEASE.2025-04-22T22-12-26Z-corpusflow-source" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /src/NOTICE /usr/share/minio/
COPY --from=build /source.tar.gz /usr/share/minio/source.tar.gz
# Match the original MinIO image UID so existing root-owned named volumes remain
# readable/writable. Do not silently chown user data during this image-source fix.
RUN mkdir /data
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
