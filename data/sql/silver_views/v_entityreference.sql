-- Silver view: entityreference
-- Derives from raw core_funded + los_underwriting tables.
-- Replicates translate.py logic: translate_to_entity_reference
--
-- Usage: CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.entityreference AS ...
-- Parameters: ${catalog}, ${raw_schema}, ${silver_schema}

CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.entityreference AS

WITH crd_entities AS (
    SELECT DISTINCT
        ENTITY_ID       AS entityIdentifier,
        BORROWER        AS obligorName,
        SEGMENT         AS customIndustrySector,
        STATE           AS incorporationState,
        'USA'           AS incorporationCountryCode,
        AS_OF_DATE      AS asOfDate,
        'CRD'           AS importSource
    FROM ${catalog}.${raw_schema}.core_funded
),

cl_entities AS (
    SELECT DISTINCT
        ENTITY_ID       AS entityIdentifier,
        BORROWER_NAME   AS obligorName,
        SEGMENT         AS customIndustrySector,
        STATE           AS incorporationState,
        'USA'           AS incorporationCountryCode,
        AS_OF_DATE      AS asOfDate,
        'CREDITLENS'    AS importSource
    FROM ${catalog}.${raw_schema}.los_underwriting
)

SELECT * FROM crd_entities
UNION ALL
SELECT * FROM cl_entities
