-- Phase 4: SLA Monitoring Database Updates

-- 1. Create the persistent "tasks" table for Meeting Action Items
CREATE TABLE IF NOT EXISTS tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    owner text NOT NULL DEFAULT 'Unassigned',
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz DEFAULT now()
);

-- disable RLS for tasks
ALTER TABLE tasks DISABLE ROW LEVEL SECURITY;

-- 2. Create the sla_breaches table for Monitoring outputs
CREATE TABLE IF NOT EXISTS sla_breaches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id text NOT NULL,
    task_name text NOT NULL,
    original_owner text NOT NULL,
    new_owner text NOT NULL,
    breach_time timestamptz NOT NULL,
    delay_duration text NOT NULL,
    action_taken text NOT NULL,
    email_sent boolean NOT NULL DEFAULT false,
    created_at timestamptz DEFAULT now()
);

-- disable RLS for sla_breaches
ALTER TABLE sla_breaches DISABLE ROW LEVEL SECURITY;
