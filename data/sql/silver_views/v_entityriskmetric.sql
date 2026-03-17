-- Silver view: entityriskmetric
-- Passthrough from raw entity_risk_metric table.
--
-- Usage: CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.v_entityriskmetric AS ...
-- Parameters: ${catalog}, ${raw_schema}, ${silver_schema}

CREATE OR REPLACE VIEW ${catalog}.${silver_schema}.v_entityriskmetric AS

SELECT *
FROM ${catalog}.${raw_schema}.entity_risk_metric
