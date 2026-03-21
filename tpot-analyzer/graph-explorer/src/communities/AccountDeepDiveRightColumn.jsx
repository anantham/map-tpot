import TweetPreviewCard from './TweetPreviewCard'
import { groupAccountsByPrimaryCommunity, sectionHeaderStyle } from './accountDeepDiveUtils'

function AccountChip({ account, background, color, title }) {
  return (
    <span
      style={{
        fontSize: 12,
        padding: '2px 6px',
        borderRadius: 4,
        background,
        color,
      }}
      title={title}
    >
      @{account.username || account.account_id.slice(0, 8)}
      {account.tpot_score != null && (
        <span style={{ fontSize: 10, color: '#64748b', marginLeft: 4 }}>
          {account.tpot_score}
        </span>
      )}
    </span>
  )
}

function GroupedAccountSection({
  title,
  countLabel,
  grouped,
  ungrouped,
  emptyLabel,
  chipBackground,
  chipColor,
  titleBuilder,
}) {
  return (
    <div>
      <div style={sectionHeaderStyle}>
        {title} ({countLabel})
      </div>
      {countLabel === 0 ? (
        <div style={{ fontSize: 12, color: '#475569' }}>{emptyLabel}</div>
      ) : (
        <>
          {Object.entries(grouped)
            .sort((left, right) => right[1].members.length - left[1].members.length)
            .map(([communityId, group]) => (
              <div key={communityId} style={{ marginBottom: 10 }}>
                <div style={{
                  fontSize: 11,
                  fontWeight: 600,
                  marginBottom: 4,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}>
                  <span style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: group.color || '#64748b',
                  }} />
                  {group.name} ({group.members.length})
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {group.members.map((account) => (
                    <AccountChip
                      key={account.account_id}
                      account={account}
                      background={chipBackground}
                      color={chipColor}
                      title={titleBuilder(account)}
                    />
                  ))}
                </div>
              </div>
            ))}
          {ungrouped.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: '#64748b' }}>
                Not in any community ({ungrouped.length})
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {ungrouped.map((account) => (
                  <AccountChip
                    key={account.account_id}
                    account={account}
                    background="rgba(148,163,184,0.1)"
                    color="#94a3b8"
                    title={titleBuilder(account)}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function AccountDeepDiveRightColumn({ preview, sections, egoAccountId }) {
  const followers = groupAccountsByPrimaryCommunity(preview.followers_you_know || [])
  const followees = groupAccountsByPrimaryCommunity(preview.notable_followees || [])

  return (
    <div>
      {sections.followersYouKnow && (
        <GroupedAccountSection
          title="People You Follow Who Follow Them"
          countLabel={preview.followers_you_know_count}
          grouped={followers.grouped}
          ungrouped={followers.ungrouped}
          emptyLabel={egoAccountId ? 'None found' : 'Set ego handle above to see this'}
          chipBackground="rgba(59,130,246,0.1)"
          chipColor="#93c5fd"
          titleBuilder={(account) => account.bio || ''}
        />
      )}

      {sections.notableFollowees && preview.notable_followees?.length > 0 && (
        <GroupedAccountSection
          title="High-TPOT Accounts They Follow"
          countLabel={preview.notable_followees.length}
          grouped={followees.grouped}
          ungrouped={followees.ungrouped}
          emptyLabel="None found"
          chipBackground="rgba(34,197,94,0.1)"
          chipColor="#86efac"
          titleBuilder={(account) => `TPOT ${account.tpot_score} · ${account.bio || ''}`}
        />
      )}

      {sections.topTweets && preview.top_tweets?.length > 0 && (
        <div>
          <div style={sectionHeaderStyle}>Top Tweets (by likes)</div>
          {preview.top_tweets.map((tweet, index) => (
            <TweetPreviewCard key={`${tweet.text}-${index}`} tweet={tweet} />
          ))}
        </div>
      )}
    </div>
  )
}
