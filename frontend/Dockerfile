FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /app/
COPY app.js /app/
COPY chat-widget.js /app/
COPY styles.css /app/

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]