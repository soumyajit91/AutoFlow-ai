-- 1. Update existing_employees
ALTER TABLE existing_employees 
ADD COLUMN IF NOT EXISTS role text,
ADD COLUMN IF NOT EXISTS department text;

-- 2. Update new_employees
ALTER TABLE new_employees 
ADD COLUMN IF NOT EXISTS role text,
ADD COLUMN IF NOT EXISTS department text;

-- 3. Create onboarding_tasks table
CREATE TABLE IF NOT EXISTS onboarding_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department text NOT NULL,
  role text NOT NULL,
  task_list jsonb NOT NULL,
  created_at timestamptz DEFAULT now(),
  UNIQUE(department, role)
);

-- disable RLS for the new table
ALTER TABLE onboarding_tasks DISABLE ROW LEVEL SECURITY;
