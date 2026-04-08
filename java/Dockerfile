# ── Build stage ───────────────────────────────────────────────────────────────
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
# Download dependencies first (better layer caching)
RUN mvn dependency:go-offline -q
COPY src ./src
RUN mvn package -DskipTests -q

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app

# Install yt-dlp + ffmpeg (required for media download/conversion)
RUN apk add --no-cache python3 py3-pip ffmpeg && \
    pip3 install --break-system-packages yt-dlp && \
    yt-dlp --version

# Copy the built jar
COPY --from=build /app/target/ytttins-dl-*.jar app.jar

# Persistent volumes
VOLUME ["/app/downloads", "/app/data", "/app/logs"]

EXPOSE 8443

ENTRYPOINT ["java", "-jar", "app.jar"]
