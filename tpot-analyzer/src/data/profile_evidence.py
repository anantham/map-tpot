"""Search passages from already-qualified profile observations of one account."""


def profile_fragments(observations):
    """One representative per exact field/text;inputs retain their source order.

    The caller qualifies every observation before this projection. Older text
    does not replace the selected display profile or gain direct-bio rank.
    """
    labels={'username':'X handle','displayName':'Display name','bio':'Profile bio',
        'location':'Self-described profile location, historical','website':'Profile website link'}
    result=[];seen=set()
    for profile in observations:
        source={key:profile[key] for key in ('sourceKind','sourceLabel','sourceBoundary','archiveExportId')
            if key in profile}
        for field,label in labels.items():
            text=profile.get(field)
            if not text or (field,text) in seen:continue
            seen.add((field,text))
            result.append({'kind':'profile','label':label,'text':text,
                'evidenceRef':profile['evidenceRef'],**source})
    return result
