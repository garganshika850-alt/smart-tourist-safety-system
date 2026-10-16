-- ============================================================
-- Smart Tourist Safety and Emergency Response System
-- PostgreSQL Relational Database Schema DDL
-- Specification: 3NF Compliant, Strict Referential Integrity
-- ============================================================

-- Clean tear-down in reverse dependency order for idempotency
DROP TABLE IF EXISTS emergency_logs CASCADE;
DROP TABLE IF EXISTS resource_assignments CASCADE;
DROP TABLE IF EXISTS resources CASCADE;
DROP TABLE IF EXISTS rescue_teams CASCADE;
DROP TABLE IF EXISTS locations CASCADE;
DROP TABLE IF EXISTS safe_dangerous_zones CASCADE;
DROP TABLE IF EXISTS emergency_incidents CASCADE;
DROP TABLE IF EXISTS emergency_contacts CASCADE;
DROP TABLE IF EXISTS tourists CASCADE;

-- ============================================================
-- 1. TOURISTS
-- Holds profile and contact information for registered tourists.
-- ============================================================
CREATE TABLE tourists (
    tourist_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    nationality VARCHAR(50),
    blood_group VARCHAR(10),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 2. EMERGENCY CONTACTS
-- Secondary contacts associated with a tourist (1:N, CASCADE on delete).
-- ============================================================
CREATE TABLE emergency_contacts (
    contact_id SERIAL PRIMARY KEY,
    tourist_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    relationship VARCHAR(50) NOT NULL,
    CONSTRAINT fk_contacts_tourist
        FOREIGN KEY (tourist_id)
        REFERENCES tourists (tourist_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- ============================================================
-- 3. SAFE & DANGEROUS ZONES
-- Geofence boundaries defining safe havens and hazardous areas.
-- ============================================================


-- ============================================================
-- 4. LOCATIONS
-- Periodic GPS telemetry reported from tourist mobile apps.
-- ============================================================


-- ============================================================
-- 5. EMERGENCY INCIDENTS
-- Central repository for all distress events, SOS alerts, and accidents.
-- Priority: 1 (Critical Accident) to 5 (GPS Update)
-- ============================================================
CREATE TABLE emergency_incidents (
    incident_id SERIAL PRIMARY KEY,
    tourist_id INT NOT NULL,
    incident_type VARCHAR(50) NOT NULL,
    priority INT NOT NULL,
    status VARCHAR(30) NOT NULL,
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT fk_incidents_tourist
        FOREIGN KEY (tourist_id)
        REFERENCES tourists (tourist_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    CONSTRAINT chk_incident_type CHECK (
        incident_type IN ('CRITICAL_ACCIDENT', 'SOS', 'DANGEROUS_ZONE', 'SAFETY_ALERT', 'GPS_UPDATE')
    ),
    CONSTRAINT chk_incident_priority CHECK (priority BETWEEN 1 AND 5),
    CONSTRAINT chk_incident_status CHECK (
        status IN ('RECEIVED', 'QUEUED', 'PROCESSING', 'RESOURCE_ASSIGNED', 'RESOLVED', 'FAILED')
    )
);

-- ============================================================
-- 6. EMERGENCY LOGS
-- Immutable system audit trail capturing scheduling & transactional lifecycle.
-- ============================================================
CREATE TABLE emergency_logs (
    log_id SERIAL PRIMARY KEY,
    incident_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    details TEXT,
    performed_by VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_logs_incident
        FOREIGN KEY (incident_id)
        REFERENCES emergency_incidents (incident_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- ============================================================
-- 7. RESCUE TEAMS
-- Personnel units available for dispatch (paramedics, SAR, firefighters).
-- ============================================================
CREATE TABLE rescue_teams (
    team_id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    specialization VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_capacity INT NOT NULL DEFAULT 0,
    max_capacity INT NOT NULL,
    contact_number VARCHAR(20) NOT NULL,
    CONSTRAINT chk_team_specialization CHECK (
        specialization IN ('MEDICAL', 'SEARCH_AND_RESCUE', 'FIRE', 'GENERAL')
    ),
    CONSTRAINT chk_team_status CHECK (
        status IN ('AVAILABLE', 'BUSY', 'OFF_DUTY')
    ),
    CONSTRAINT chk_team_current_capacity CHECK (current_capacity >= 0),
    CONSTRAINT chk_team_capacity_limits CHECK (
        max_capacity > 0 AND max_capacity >= current_capacity
    )
);


-- ============================================================
-- 8. RESOURCES
-- Physical emergency equipment and vehicles (ambulances, helicopters).
-- ============================================================
CREATE TABLE resources (
    resource_id SERIAL PRIMARY KEY,
    resource_name VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_lat DECIMAL(9, 6),
    current_lng DECIMAL(9, 6),
    CONSTRAINT chk_resource_type CHECK (
        resource_type IN ('AMBULANCE', 'HELICOPTER', 'FIRE_TRUCK', 'RESCUE_BOAT')
    ),
    CONSTRAINT chk_resource_status CHECK (
        status IN ('AVAILABLE', 'ASSIGNED', 'MAINTENANCE', 'OUT_OF_SERVICE')
    )
);

-- ============================================================
-- 9. RESOURCE ASSIGNMENTS
-- Junction entity tracking resource/team dispatches to emergency incidents.
-- ============================================================
CREATE TABLE resource_assignments (
    assignment_id SERIAL PRIMARY KEY,
    incident_id INT NOT NULL,
    resource_id INT,
    team_id INT,
    status VARCHAR(30) NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMPTZ,
    CONSTRAINT fk_assignments_incident
        FOREIGN KEY (incident_id)
        REFERENCES emergency_incidents (incident_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT fk_assignments_resource
        FOREIGN KEY (resource_id)
        REFERENCES resources (resource_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,
    CONSTRAINT fk_assignments_team
        FOREIGN KEY (team_id)
        REFERENCES rescue_teams (team_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,
    CONSTRAINT chk_assignment_target CHECK (
        resource_id IS NOT NULL OR team_id IS NOT NULL
    ),
    CONSTRAINT chk_assignment_status CHECK (
        status IN ('ASSIGNED', 'EN_ROUTE', 'ON_SITE', 'COMPLETED', 'CANCELLED')
    )
);


-- Prevent duplicate active assignment of the same physical resource to an incident
CREATE UNIQUE INDEX uq_incident_resource ON resource_assignments (incident_id, resource_id) 
WHERE resource_id IS NOT NULL;

-- ============================================================
-- PERFORMANCE & OPERATIONAL INDEXES (B-TREE)
-- ============================================================

-- Emergency Incidents query optimization (Priority Queue, Dashboard)
CREATE INDEX idx_incident_status ON emergency_incidents (status);
CREATE INDEX idx_incident_priority ON emergency_incidents (priority);
CREATE INDEX idx_incident_tourist ON emergency_incidents (tourist_id);
CREATE INDEX idx_incident_created ON emergency_incidents (created_at DESC);

-- Location query optimization (Latest location retrieval)
CREATE INDEX idx_location_tourist_time ON locations (tourist_id, recorded_at DESC);
CREATE INDEX idx_location_zone ON locations (zone_id);

-- Foreign key lookup optimization
CREATE INDEX idx_contact_tourist ON emergency_contacts (tourist_id);

-- Resource availability & Banker's Algorithm optimization
CREATE INDEX idx_resource_status ON resources (status);
CREATE INDEX idx_resource_type ON resources (resource_type);
CREATE INDEX idx_team_status ON rescue_teams (status);

-- Assignment & Audit log traversal
CREATE INDEX idx_assignment_incident ON resource_assignments (incident_id);
CREATE INDEX idx_assignment_resource ON resource_assignments (resource_id);
CREATE INDEX idx_assignment_team ON resource_assignments (team_id);
CREATE INDEX idx_emergency_log_incident ON emergency_logs (incident_id, created_at DESC);
