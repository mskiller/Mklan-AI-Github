import psycopg

views = [
    ('source_files', 'wildcard_source_files'),
    ('entries', 'wildcard_entries'),
    ('entry_history', 'wildcard_entry_history'),
    ('scan_runs', 'wildcard_scan_runs'),
    ('tag_index', 'wildcard_tag_index'),
    ('category_index', 'wildcard_category_index'),
    ('category_stats', 'wildcard_category_stats'),
    ('prompt_mode_index', 'wildcard_prompt_mode_index'),
    ('prompt_recipes', 'wildcard_prompt_recipes'),
    ('tag_overrides', 'wildcard_tag_overrides'),
    ('taxonomy_rules', 'wildcard_taxonomy_rules'),
    ('taxonomy_meta', 'wildcard_taxonomy_meta'),
    ('source_file_stats', 'wildcard_source_file_stats'),
    ('llm_jobs', 'wildcard_llm_jobs'),
    ('tag_polarity_index', 'wildcard_tag_polarity_index')
]

with psycopg.connect('postgresql://mklan_studio:change-me@studio_db:5432/mklan_studio') as conn:
    for view, table in views:
        conn.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM {table} WHERE workspace_id = 'default' WITH CHECK OPTION;")
    conn.commit()
print('Views created successfully!')
