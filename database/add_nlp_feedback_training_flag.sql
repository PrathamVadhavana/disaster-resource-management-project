-- Add used_in_training column to nlp_training_feedback table
-- This column tracks which feedback rows have been used for ML model training

ALTER TABLE public.nlp_training_feedback 
ADD COLUMN IF NOT EXISTS used_in_training BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_nlp_feedback_unused 
ON public.nlp_training_feedback(used_in_training) 
WHERE used_in_training = FALSE;

COMMENT ON COLUMN public.nlp_training_feedback.used_in_training 
IS 'Whether this feedback row has been used for training the ML model';
