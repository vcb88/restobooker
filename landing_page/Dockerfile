# Use a lightweight Nginx image to serve the static files
FROM nginx:alpine

# Copy the static files (HTML, CSS) into the Nginx web root directory
COPY . /usr/share/nginx/html

# Set correct permissions for Nginx to serve the files
RUN chmod -R a+rX /usr/share/nginx/html

# Expose port 80 for web traffic
EXPOSE 80

# Command to run Nginx (default in nginx:alpine image)
CMD ["nginx", "-g", "daemon off;"]