CREATE SCHEMA IF NOT EXISTS synthea;

-- ---------------------------------------------------------------------
-- patients
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS synthea.patients (
    patient_id   VARCHAR(64)   NOT NULL,   -- FHIR resource IDs are UUIDs; 64 leaves headroom
    gender       VARCHAR(16),
    birth_date   DATE,
    first_name   VARCHAR(128),
    last_name    VARCHAR(128),
    city         VARCHAR(128),
    state        VARCHAR(64),
    PRIMARY KEY (patient_id)
)
DISTSTYLE KEY
DISTKEY (patient_id)
SORTKEY (patient_id);

-- ---------------------------------------------------------------------
-- encounters
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS synthea.encounters (
    encounter_id     VARCHAR(64)   NOT NULL,
    patient_id       VARCHAR(64)   NOT NULL,
    status           VARCHAR(32),
    encounter_type   VARCHAR(256),
    start_time       TIMESTAMP,
    end_time         TIMESTAMP,
    PRIMARY KEY (encounter_id)
)
DISTSTYLE KEY
DISTKEY (patient_id)          -- colocates with patients for cheap joins
SORTKEY (start_time);         -- encounters are commonly filtered/ordered by time

-- ---------------------------------------------------------------------
-- conditions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS synthea.conditions (
    condition_id          VARCHAR(64)   NOT NULL,
    patient_id            VARCHAR(64)   NOT NULL,
    condition_code        VARCHAR(32),
    condition_description VARCHAR(512),
    onset_date             DATE,
    clinical_status        VARCHAR(32),
    PRIMARY KEY (condition_id)
)
DISTSTYLE KEY
DISTKEY (patient_id)
SORTKEY (onset_date);

-- ---------------------------------------------------------------------
-- observations
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS synthea.observations (
    observation_id     VARCHAR(64)   NOT NULL,
    patient_id         VARCHAR(64)   NOT NULL,
    encounter_id       VARCHAR(64),
    observation_name   VARCHAR(256),
    observed_at         TIMESTAMP,
    value               VARCHAR(256),   -- stored as text: source values are numeric,
                                         -- string, or coded (coalesced upstream in Glue)
    unit                VARCHAR(32),
    PRIMARY KEY (observation_id)
)
DISTSTYLE KEY
DISTKEY (patient_id)
SORTKEY (observed_at);
