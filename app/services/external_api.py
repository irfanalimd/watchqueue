"""External API clients for movie/show metadata."""

import asyncio
from dataclasses import dataclass
from typing import Any
import httpx
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class MovieInfo:
    """Movie information from TMDB."""
    tmdb_id: int
    title: str
    poster_url: str | None
    year: int | None
    runtime_minutes: int | None
    genres: list[str]
    overview: str | None
    vote_average: float | None = None
    media_type: str = "movie"


@dataclass
class StreamingInfo:
    """Streaming availability information."""
    provider_name: str
    provider_logo: str | None
    link: str | None


class TMDBClient:
    """Client for The Movie Database API.

    Handles fetching movie/show metadata including posters, genres, runtime.
    """

    _genre_cache: dict[int, str] = {}

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.tmdb_api_key
        self.base_url = base_url or settings.tmdb_base_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=10.0,
                params={"api_key": self.api_key},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_movie(self, query: str) -> MovieInfo | None:
        """Search for a movie by title.

        Returns the first matching result.
        """
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return None

        try:
            client = await self._get_client()
            response = await client.get(
                "/search/movie",
                params={"query": query},
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                return None

            movie = results[0]
            return await self._parse_movie(movie)

        except httpx.HTTPError as e:
            logger.error(f"TMDB search failed: {e}")
            return None

    async def get_genre_map(self) -> dict[int, str]:
        """Get cached genre ID to name mapping from TMDB."""
        if TMDBClient._genre_cache:
            return TMDBClient._genre_cache
        if not self.api_key:
            return {}
        try:
            client = await self._get_client()
            response = await client.get("/genre/movie/list")
            response.raise_for_status()
            for g in response.json().get("genres", []):
                TMDBClient._genre_cache[g["id"]] = g["name"]
            # Also fetch TV genres
            response = await client.get("/genre/tv/list")
            response.raise_for_status()
            for g in response.json().get("genres", []):
                if g["id"] not in TMDBClient._genre_cache:
                    TMDBClient._genre_cache[g["id"]] = g["name"]
        except httpx.HTTPError as e:
            logger.error(f"TMDB genre fetch failed: {e}")
        return TMDBClient._genre_cache

    async def search_multi(self, query: str, limit: int = 8) -> list[MovieInfo]:
        """Search TMDB for movies and TV shows, returning multiple results."""
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return []

        try:
            client = await self._get_client()
            genre_map = await self.get_genre_map()

            response = await client.get(
                "/search/multi",
                params={"query": query},
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for item in data.get("results", []):
                media_type = item.get("media_type")
                if media_type == "movie":
                    poster_path = item.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                    release_date = item.get("release_date", "")
                    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
                    genres = [genre_map[gid] for gid in item.get("genre_ids", []) if gid in genre_map]
                    results.append(MovieInfo(
                        tmdb_id=item["id"],
                        title=item.get("title", ""),
                        poster_url=poster_url,
                        year=year,
                        runtime_minutes=None,
                        genres=genres,
                        overview=item.get("overview"),
                        vote_average=item.get("vote_average"),
                        media_type="movie",
                    ))
                elif media_type == "tv":
                    poster_path = item.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                    first_air = item.get("first_air_date", "")
                    year = int(first_air[:4]) if first_air and len(first_air) >= 4 else None
                    genres = [genre_map[gid] for gid in item.get("genre_ids", []) if gid in genre_map]
                    results.append(MovieInfo(
                        tmdb_id=item["id"],
                        title=item.get("name", item.get("original_name", "")),
                        poster_url=poster_url,
                        year=year,
                        runtime_minutes=None,
                        genres=genres,
                        overview=item.get("overview"),
                        vote_average=item.get("vote_average"),
                        media_type="tv",
                    ))

                if len(results) >= limit:
                    break

            return results

        except httpx.HTTPError as e:
            logger.error(f"TMDB multi search failed: {e}")
            return []

    async def get_movie(self, tmdb_id: int) -> MovieInfo | None:
        """Get movie details by TMDB ID."""
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return None

        try:
            client = await self._get_client()
            response = await client.get(f"/movie/{tmdb_id}")
            response.raise_for_status()

            movie = response.json()
            return await self._parse_movie(movie, full_details=True)

        except httpx.HTTPError as e:
            logger.error(f"TMDB get movie failed: {e}")
            return None

    async def get_tv(self, tmdb_id: int) -> MovieInfo | None:
        """Get TV show details by TMDB ID."""
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return None

        try:
            client = await self._get_client()
            response = await client.get(f"/tv/{tmdb_id}")
            response.raise_for_status()
            show = response.json()
            return MovieInfo(
                tmdb_id=show["id"],
                title=show.get("name", show.get("original_name", "")),
                poster_url=(
                    f"https://image.tmdb.org/t/p/w500{show['poster_path']}"
                    if show.get("poster_path")
                    else None
                ),
                year=int(show["first_air_date"][:4]) if show.get("first_air_date") else None,
                runtime_minutes=((show.get("episode_run_time") or [None])[0]),
                genres=[g["name"] for g in show.get("genres", [])],
                overview=show.get("overview"),
                vote_average=show.get("vote_average"),
                media_type="tv",
            )
        except httpx.HTTPError as e:
            logger.error(f"TMDB get TV failed: {e}")
            return None

    async def get_watch_providers(self, tmdb_id: int, media_type: str) -> dict[str, dict[str, Any]]:
        """Get watch providers by region for a movie or TV show."""
        if not self.api_key:
            return {}

        endpoint_type = "tv" if media_type == "tv" else "movie"

        try:
            client = await self._get_client()
            response = await client.get(f"/{endpoint_type}/{tmdb_id}/watch/providers")
            response.raise_for_status()
            data = response.json()
            results = data.get("results", {})

            normalized: dict[str, dict[str, Any]] = {}
            for region, payload in results.items():
                providers: list[dict[str, Any]] = []
                for access_type in ("flatrate", "ads", "free", "rent", "buy"):
                    for provider in payload.get(access_type, []) or []:
                        logo_path = provider.get("logo_path")
                        providers.append(
                            {
                                "provider_name": provider.get("provider_name"),
                                "provider_logo": (
                                    f"https://image.tmdb.org/t/p/w500{logo_path}"
                                    if logo_path
                                    else None
                                ),
                                "access_type": access_type,
                            }
                        )

                normalized[region.upper()] = {
                    "link": payload.get("link"),
                    "providers": providers,
                }
            return normalized
        except httpx.HTTPError as e:
            logger.error(f"TMDB watch providers failed: {e}")
            return {}

    async def _parse_movie(
        self,
        movie: dict[str, Any],
        full_details: bool = False,
    ) -> MovieInfo:
        """Parse movie data from TMDB response."""
        poster_path = movie.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        release_date = movie.get("release_date", "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

        # Genre names come differently in search vs details
        if full_details:
            genres = [g["name"] for g in movie.get("genres", [])]
            runtime = movie.get("runtime")
        else:
            genres = []  # Search results only have genre_ids
            runtime = None

        return MovieInfo(
            tmdb_id=movie["id"],
            title=movie["title"],
            poster_url=poster_url,
            year=year,
            runtime_minutes=runtime,
            genres=genres,
            overview=movie.get("overview"),
            vote_average=movie.get("vote_average"),
            media_type="movie",
        )

    async def search_tv(self, query: str) -> MovieInfo | None:
        """Search for a TV show by title."""
        if not self.api_key:
            return None

        try:
            client = await self._get_client()
            response = await client.get(
                "/search/tv",
                params={"query": query},
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                return None

            show = results[0]
            return await self._parse_tv(show)

        except httpx.HTTPError as e:
            logger.error(f"TMDB TV search failed: {e}")
            return None

    async def _parse_tv(self, show: dict[str, Any]) -> MovieInfo:
        """Parse TV show data from TMDB response."""
        poster_path = show.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        first_air = show.get("first_air_date", "")
        year = int(first_air[:4]) if first_air and len(first_air) >= 4 else None

        return MovieInfo(
            tmdb_id=show["id"],
            title=show.get("name", show.get("original_name", "")),
            poster_url=poster_url,
            year=year,
            runtime_minutes=None,  # TV shows don't have a single runtime
            genres=[],
            overview=show.get("overview"),
            vote_average=show.get("vote_average"),
            media_type="tv",
        )

    async def search(self, query: str) -> MovieInfo | None:
        """Search for a movie or TV show.

        Searches movies first, falls back to TV if no results.
        """
        result = await self.search_movie(query)
        if result:
            return result
        return await self.search_tv(query)


class StreamingAvailabilityClient:
    """Client for checking streaming availability.

    Note: JustWatch doesn't have a public API, so this is a placeholder
    that could be implemented with a third-party service or scraping solution.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_availability(self, title: str) -> list[str]:
        """Get streaming availability for a title.

        Returns list of provider names where the title is available.
        This is a placeholder - implement with actual API.
        """
        # Placeholder implementation
        # In production, integrate with a streaming availability API
        return []

    async def check_provider(self, title: str, provider: str) -> bool:
        """Check if title is available on specific provider."""
        availability = await self.get_availability(title)
        return provider.lower() in [p.lower() for p in availability]


async def enrich_queue_item(
    title: str,
    tmdb_id: int | None = None,
    member_regions: list[str] | None = None,
    tmdb_client: TMDBClient | None = None,
    streaming_client: StreamingAvailabilityClient | None = None,
) -> dict[str, Any]:
    """Fetch movie details from multiple sources concurrently.

    Returns enrichment data that can be used to update a queue item.
    Handles failures gracefully - returns partial data if some APIs fail.
    """
    own_tmdb = tmdb_client is None
    own_streaming = streaming_client is None

    if own_tmdb:
        tmdb_client = TMDBClient()
    if own_streaming:
        streaming_client = StreamingAvailabilityClient()

    try:
        settings = get_settings()
        default_region = settings.default_region.upper()
        regions = {
            default_region,
            *(r.upper() for r in (member_regions or []) if r),
        }

        if tmdb_id:
            movie_task = asyncio.create_task(tmdb_client.get_movie(tmdb_id))
            streaming_task = asyncio.create_task(streaming_client.get_availability(title))
            movie_info, streaming = await asyncio.gather(
                movie_task,
                streaming_task,
                return_exceptions=True,
            )
            if movie_info is None:
                movie_info = await tmdb_client.get_tv(tmdb_id)
            if movie_info is None:
                movie_info = await tmdb_client.search(title)
        else:
            tmdb_task = asyncio.create_task(tmdb_client.search(title))
            streaming_task = asyncio.create_task(streaming_client.get_availability(title))
            movie_info, streaming = await asyncio.gather(
                tmdb_task,
                streaming_task,
                return_exceptions=True,
            )

        result: dict[str, Any] = {}

        # Handle TMDB results
        if isinstance(movie_info, MovieInfo):
            result["tmdb_id"] = movie_info.tmdb_id
            result["poster_url"] = movie_info.poster_url
            result["year"] = movie_info.year
            result["runtime_minutes"] = movie_info.runtime_minutes
            result["genres"] = movie_info.genres
            result["vote_average"] = movie_info.vote_average

            watch_providers = await tmdb_client.get_watch_providers(
                movie_info.tmdb_id,
                movie_info.media_type,
            )
            providers_by_region: dict[str, list[str]] = {}
            provider_links: list[dict[str, Any]] = []
            for region in regions:
                region_data = watch_providers.get(region, {})
                region_providers = [
                    p.get("provider_name")
                    for p in region_data.get("providers", [])
                    if p.get("provider_name")
                ]
                providers_by_region[region] = sorted(set(region_providers))
                if region == default_region:
                    link = region_data.get("link")
                    for provider in region_data.get("providers", []):
                        provider_name = provider.get("provider_name")
                        if not provider_name:
                            continue
                        provider_links.append(
                            {
                                "provider_name": provider_name,
                                "provider_logo": provider.get("provider_logo"),
                                "region": region,
                                "access_type": provider.get("access_type", "flatrate"),
                                "link": link,
                            }
                        )

                    result["streaming_on"] = sorted(set(providers_by_region.get(region, [])))
                    result["play_now_url"] = link

            result["providers_by_region"] = providers_by_region
            result["provider_links"] = provider_links
        elif isinstance(movie_info, Exception):
            logger.warning(f"TMDB enrichment failed for '{title}': {movie_info}")

        # Handle streaming results
        if isinstance(streaming, list) and streaming and "streaming_on" not in result:
            result["streaming_on"] = streaming
        elif isinstance(streaming, Exception):
            logger.warning(f"Streaming enrichment failed for '{title}': {streaming}")

        return result

    finally:
        if own_tmdb:
            await tmdb_client.close()
        if own_streaming:
            await streaming_client.close()
