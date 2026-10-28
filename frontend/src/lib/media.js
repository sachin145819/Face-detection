export const isVideoItem = (item) => item?.media_type === 'video'

/** Route to the right result page for a HistoryItem (image or video). */
export function resultPath(item) {
  return isVideoItem(item) ? `/video-analyses/${item.analysis_id}` : `/analyses/${item.analysis_id}`
}

/** Stable React key: image and video analysis ids can collide. */
export const itemKey = (item) => `${item?.media_type || 'image'}-${item?.analysis_id}`
