# Production Dockerfile for n8n on Render.com
FROM n8nio/n8n:latest

USER root
RUN apk add --no-co-cache curl bash jq

USER node
EXPOSE 5678
CMD ["n8n", "start"]
