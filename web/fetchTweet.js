// Native Supabase fetcher module, wired to your project
// Exports: fetchRandomTweet() -> { tweet_id, username, created_at_utc_iso, full_text }

const supabaseUrl = 'https://fabxmporizzqflnftavs.supabase.co';
// Public anon key copied from your existing helper
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0.UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8';

// Uses the UMD client already included in index.html
const client = window.supabase.createClient(supabaseUrl, supabaseKey);

export async function fetchRandomTweet() {
  // Get total count of tweets to sample a random offset
  const { count, error: countErr } = await client
    .from('tweets')
    .select('tweet_id', { count: 'exact', head: true });
  if (countErr) throw countErr;
  const total = count || 0;
  if (!total) throw new Error('No tweets available in archive');
  const offset = Math.floor(Math.random() * total);

  const { data, error } = await client
    .from('tweets')
    .select('*')
    .range(offset, offset)
    .limit(1);
  if (error) throw error;
  const t = data?.[0];
  if (!t) throw new Error('Random selection failed');

  const { data: acc } = await client
    .from('account')
    .select('*')
    .eq('account_id', t.account_id)
    .limit(1);
  const username = acc?.[0]?.username || 'user';

  return {
    tweet_id: t.tweet_id,
    username,
    created_at_utc_iso: t.created_at,
    full_text: t.full_text,
  };
}

