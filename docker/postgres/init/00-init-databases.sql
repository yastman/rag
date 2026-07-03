-- Dev Stack: Auto-create databases for services
-- This script runs automatically on first PostgreSQL start

-- Database for Real Estate CRM/Funnel
CREATE DATABASE realestate;
GRANT ALL PRIVILEGES ON DATABASE realestate TO postgres;
