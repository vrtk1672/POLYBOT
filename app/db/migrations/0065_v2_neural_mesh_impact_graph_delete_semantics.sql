ALTER TABLE impact_links DROP CONSTRAINT IF EXISTS impact_links_signal_id_fkey;

ALTER TABLE impact_links
    ADD CONSTRAINT impact_links_signal_id_fkey
    FOREIGN KEY (signal_id)
    REFERENCES neuron_signals(signal_id)
    ON DELETE CASCADE;

ALTER TABLE impact_links DROP CONSTRAINT IF EXISTS impact_links_entity_id_fkey;

ALTER TABLE impact_links
    ADD CONSTRAINT impact_links_entity_id_fkey
    FOREIGN KEY (entity_id)
    REFERENCES event_entities(entity_id)
    ON DELETE CASCADE;

ALTER TABLE impact_links DROP CONSTRAINT IF EXISTS impact_links_thesis_id_fkey;

ALTER TABLE impact_links
    ADD CONSTRAINT impact_links_thesis_id_fkey
    FOREIGN KEY (thesis_id)
    REFERENCES position_thesis_profiles(thesis_id)
    ON DELETE CASCADE;
