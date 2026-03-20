# VPS Deployment Guide

## Prerequisites
- A VPS (Ubuntu 22.04 recommended)
- A domain name pointed to your VPS IP

## Initial Server Setup
1. SSH into your server:
   `ssh root@your_server_ip`
2. Update packages:
   `sudo apt update && sudo apt upgrade -y`
3. Install Docker:
   `sudo apt install docker.io docker-compose -y`
4. Enable Docker to start on boot:
   `sudo systemctl enable --now docker`

## Project Setup
1. Clone your project onto the VPS:
   `git clone <your-repo-link> carpool`
   `cd carpool`
2. Create a `.env` file for your environment variables (DB_NAME, DB_USER, etc)
   `cp .env.example .env` (if provided, else create manually)

## SSL Setup (Let's Encrypt / Certbot)
To get HTTPS using Let's Encrypt:
1. Install Certbot: `sudo apt install certbot python3-certbot-nginx -y`
2. (You will need Nginx on the host temporarily or using a standalone certbot image).
Using the docker setup, an easier way is to map the certs into Nginx.
Alternatively, use `nginx-proxy` and `acme-companion` docker images for auto-SSL.
For a basic Nginx-certbot wrapper inside your VPS:
`sudo certbot --nginx -d yourdomain.com`

## Starting the App
1. Run docker-compose up:
   `docker-compose up -d --build`
2. Run database migrations inside the container:
   `docker-compose exec web python manage.py migrate`
3. Collect static files:
   `docker-compose exec web python manage.py collectstatic --no-input`

Your graph-based carpooling system is now online!
