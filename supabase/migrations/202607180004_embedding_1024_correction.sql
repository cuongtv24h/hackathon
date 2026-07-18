-- Align deployed environments with the MVP Jina embedding contract.
-- Existing vectors with a non-1024 dimension cannot be transformed safely;
-- they are cleared and must be recreated by the approved WP-008 ingestion.

do $$
declare
  current_typmod integer;
begin
  select atttypmod into current_typmod
    from pg_attribute
   where attrelid = 'public.knowledge_chunks'::regclass
     and attname = 'embedding'
     and not attisdropped;

  if current_typmod is distinct from 1024 then
    drop index if exists knowledge_chunks_embedding_idx;
    alter table knowledge_chunks
      alter column embedding type vector(1024) using null;
    raise notice 'knowledge_chunks.embedding reset to vector(1024); rerun WP-008 ingestion before enabling RAG.';
  end if;
end $$;

create index if not exists knowledge_chunks_embedding_idx
  on knowledge_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
