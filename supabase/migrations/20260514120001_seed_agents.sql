-- ============================================================================
-- Fiverr AI Agency — Agent registry seed
-- ============================================================================
-- Registers all 19 agents across the 6 pipeline layers and primes
-- `agent_status` so the dashboard renders an empty grid before any order
-- arrives.
--
-- This is a migration (not a seed.sql file) because the agent registry is
-- production data, not test fixtures. Agent IDs must be stable across envs.
--
-- `handles_service_types` enables data-driven routing in the orchestrator —
-- only generation agents declare what they handle; coordination, creative,
-- editing, QC, and delivery agents act on every order and leave the array
-- empty.
--
-- Layout coordinates (`position_x`, `position_y`) target a 1600px-wide
-- @xyflow/react viewport with 280px between layer columns.
-- ============================================================================

insert into agents (agent_key, display_name, layer, description, layer_order,
                    position_x, position_y, handles_service_types) values
  -- ── Layer 1: Coordination ──────────────────────────────────────────────
  ('orchestrator',         'Master Orchestrator',       'coordination',
    'Routes orders and coordinates all agents using LangGraph state machine.',
    1,    0,   0, '{}'),
  ('intake_parser',        'Intake Parser',             'coordination',
    'Parses Fiverr order emails (n8n + Claude) into structured order rows.',
    2,    0, 120, '{}'),
  ('brief_clarification',  'Brief Clarification',       'coordination',
    'Scores brief confidence and drafts clarification messages when ambiguous.',
    3,    0, 240, '{}'),

  -- ── Layer 2: Creative Direction ────────────────────────────────────────
  ('prompt_engineering',   'Prompt Engineering',        'creative',
    'Converts client brief into precise generation prompt using template library.',
    1,  280,  60, '{}'),
  ('style_reference',      'Style Reference Analyzer',  'creative',
    'Extracts color, mood, and composition attributes from client reference images.',
    2,  280, 180, '{}'),

  -- ── Layer 3: Generation ────────────────────────────────────────────────
  ('thumbnail_gen',        'Thumbnail Generator',       'generation',
    'YouTube thumbnails via Flux 1.1 Pro (fal.ai) + SDXL fallback.',
    1,  560,   0, '{"thumbnail"}'),
  ('social_graphics_gen',  'Social Graphics Generator', 'generation',
    'Instagram, Facebook, Twitter graphics — multi aspect ratio.',
    2,  560,  90, '{"social_graphic"}'),
  ('background_removal',   'Background Removal',        'generation',
    'Subject extraction via rembg + transparent-background.',
    3,  560, 180, '{"background_removal"}'),
  ('headshot_gen',         'AI Headshot Generator',     'generation',
    'Photorealistic headshots via Flux 1.1 Pro Ultra.',
    4,  560, 270, '{"headshot"}'),
  ('logo_gen',             'Logo Generator',            'generation',
    'SDXL + DALL-E 3 raster generation, post-processed to SVG via vtracer.',
    5,  560, 360, '{"logo"}'),
  ('business_design',      'Business Design Concept',   'generation',
    'Brand mood boards, color palettes, typography pairings via SDXL + Claude.',
    6,  560, 450, '{"business_design"}'),

  -- ── Layer 4: Editing ───────────────────────────────────────────────────
  ('image_editor',         'Image Editor',              'editing',
    'Pillow + OpenCV compositing, color grading, contrast adjustment.',
    1,  840,  90, '{}'),
  ('upscaler',             'Upscaler',                  'editing',
    'Real-ESRGAN ncnn 4x upscale to deliverable resolution.',
    2,  840, 200, '{}'),
  ('text_renderer',        'Text Renderer',             'editing',
    'Pillow-based styled text overlay (titles, captions, watermarks).',
    3,  840, 310, '{}'),

  -- ── Layer 5: Quality Control ───────────────────────────────────────────
  ('technical_qc',         'Technical QC',              'quality',
    'Dimensions, DPI, file format, file size checks via Pillow.',
    1, 1120,  90, '{}'),
  ('visual_qc',            'Visual QC',                 'quality',
    'Claude Vision review for distorted faces, hands, and text errors.',
    2, 1120, 200, '{}'),
  ('brand_consistency',    'Brand Consistency',         'quality',
    'CLIP embedding cosine similarity vs client reference (threshold 0.75).',
    3, 1120, 310, '{}'),

  -- ── Layer 6: Delivery ──────────────────────────────────────────────────
  ('delivery_packager',    'Delivery Packager',         'delivery',
    'Renames files, builds ZIP, drafts delivery message.',
    1, 1400, 140, '{}'),
  ('upsell_agent',         'Upsell Agent',              'delivery',
    'Suggests a logical next service to include in the delivery message.',
    2, 1400, 260, '{}');

-- Prime agent_status with idle state for every agent so the dashboard grid
-- renders immediately even before the first order arrives.
insert into agent_status (agent_id, current_status)
select id, 'idle' from agents;
