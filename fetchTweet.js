async function fetchTweet(tweetId) {
  const tweetContainer = document.querySelector("#tweet-container")
  tweetContainer.innerHTML = "Fetching.."
  
  const supabaseUrl = 'https://fabxmporizzqflnftavs.supabase.co'
  const supabaseKey = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0.UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8`
  const supabaseClient = window.supabase.createClient(supabaseUrl, supabaseKey)
  const { data, error } = await supabaseClient
    .schema('public')
    .from('tweets')
    .select('*')
    .eq('tweet_id', tweetId) 
    .limit(1)
  if (data.length == 0) {
      tweetContainer.innerHTML = "Tweet not found in the Community Archive"

    return
  }
  
  const tweet = data[0]
  const { created_at, account_id, favorite_count, full_text, retweet_count, tweet_id } = tweet
  
  const accountResponse = await supabaseClient.schema('public').from('account').select('*').eq('account_id', account_id)
  const { account_display_name, username } = accountResponse.data[0]
  
  const profileResponse = await supabaseClient.schema('public').from('profile').select('*').eq('account_id', account_id)
  const { avatar_media_url } = profileResponse.data[0]
  
  tweetContainer.innerHTML = `
    <tweet-component 
      avatar="${avatar_media_url}" 
      name="${account_display_name}" 
      username="${username}" 
      timestamp="${created_at}" 
      likes="${favorite_count}" 
      retweets="${retweet_count}" 
      url="https://x.com/${username}/status/${tweet_id}">
        ${full_text}
      </tweet-component>
  `
}

document.querySelector("#fetch-btn").onclick = () => {
  fetchTweet(document.querySelector("#tweet-id").value)
}
