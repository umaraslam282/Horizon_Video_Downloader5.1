from gallery_dl.extractor.instagram import InstagramExtractor, USER_PATTERN

class InstagramReelsCustomExtractor(InstagramExtractor):
    """Custom extractor for Instagram Reels without hitting blocked /info/ endpoint"""
    subcategory = "reels"
    pattern = USER_PATTERN + r"/reels(?:/.*)?"
    example = "https://www.instagram.com/USER/reels/"

    def posts(self):
        count = 0
        max_reels = 300  # Generous safety threshold to prevent hanging on massive accounts
        for reel in self.api.user_reels(self.item):
            media = reel.get("media") or reel.get("node", {}).get("media") or reel
            if not media or not isinstance(media, dict):
                continue
            
            code = media.get("code") or media.get("shortcode", "")
            pk = media.get("pk") or media.get("id", "")
            if not code or not pk:
                continue

            caption_obj = media.get("caption")
            caption_text = ""
            if isinstance(caption_obj, dict):
                caption_text = caption_obj.get("text", "")
            elif isinstance(caption_obj, str):
                caption_text = caption_obj
            
            reel_post = {
                "pk": pk,
                "code": code,
                "user": media.get("user") or self._user or {"username": self.item},
                "caption": {"text": caption_text} if caption_text else None,
                "like_count": media.get("like_count", 0),
                "play_count": media.get("play_count", 0),
                "comment_count": media.get("comment_count", 0),
                "has_liked": False,
                "product_type": "clips",
                "image_versions2": media.get("image_versions2") or {
                    "candidates": [{"url": f"https://www.instagram.com/reel/{code}/", "width": 1080, "height": 1920}]
                },
                "video_versions": [
                    {
                        "url": f"https://www.instagram.com/reel/{code}/",
                        "width": media.get("original_width", 1080),
                        "height": media.get("original_height", 1920),
                    }
                ],
                "taken_at": media.get("taken_at") or 0,
            }
            yield reel_post
            count += 1
            if count >= max_reels:
                self.log.info("Reached maximum scan limit of %d reels.", max_reels)
                break
