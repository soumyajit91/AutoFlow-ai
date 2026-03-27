-- Phase 5: Advanced SLA Monitoring

-- 1. Add requires_approval to existing tasks table
ALTER TABLE tasks 
ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN DEFAULT false;
