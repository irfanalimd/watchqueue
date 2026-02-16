"""Voting API endpoints with atomic operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.vote import Vote, VoteCreate, VoteType
from app.models.reaction import ReactionCreate
from app.services.voting import VotingService
from app.services.history import HistoryService
from app.services.reactions import ReactionService
from app.models.watch_history import WatchHistory, RatingUpdate

router = APIRouter(prefix="/votes", tags=["voting"])


def get_voting_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> VotingService:
    """Dependency for voting service."""
    return VotingService(db)


def get_history_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> HistoryService:
    """Dependency for history service."""
    return HistoryService(db)


def get_reaction_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> ReactionService:
    """Dependency for reaction service."""
    return ReactionService(db)


@router.post("", response_model=Vote, status_code=status.HTTP_201_CREATED)
async def cast_vote(
    vote_data: VoteCreate,
    service: VotingService = Depends(get_voting_service),
) -> Vote:
    """Cast or update a vote on a queue item.

    Uses atomic upsert to handle concurrent voting safely.
    If user already voted, their vote is updated.
    """
    try:
        return await service.vote(vote_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{item_id}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vote(
    item_id: str,
    user_id: str,
    service: VotingService = Depends(get_voting_service),
) -> None:
    """Remove a user's vote from an item."""
    removed = await service.remove_vote(item_id, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vote not found",
        )


@router.get("/user/{item_id}/{user_id}", response_model=Vote)
async def get_vote(
    item_id: str,
    user_id: str,
    service: VotingService = Depends(get_voting_service),
) -> Vote:
    """Get a user's vote on an item."""
    vote = await service.get_vote(item_id, user_id)
    if not vote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vote not found",
        )
    return vote


@router.get("/item/{item_id}", response_model=list[Vote])
async def get_item_votes(
    item_id: str,
    service: VotingService = Depends(get_voting_service),
) -> list[Vote]:
    """Get all votes for a queue item."""
    return await service.get_item_votes(item_id)


@router.get("/item/{item_id}/counts")
async def get_vote_counts(
    item_id: str,
    service: VotingService = Depends(get_voting_service),
) -> dict[str, int]:
    """Get vote counts for an item."""
    return await service.get_vote_counts(item_id)


@router.get("/room/{room_id}/user/{user_id}")
async def get_user_votes_in_room(
    room_id: str,
    user_id: str,
    service: VotingService = Depends(get_voting_service),
) -> dict[str, str]:
    """Get all of a user's votes in a room.

    Returns mapping of item_id to vote type.
    """
    votes = await service.get_user_votes_in_room(room_id, user_id)
    return {item_id: vote.value for item_id, vote in votes.items()}


@router.post("/reactions")
async def toggle_reaction(
    reaction_data: ReactionCreate,
    service: ReactionService = Depends(get_reaction_service),
) -> dict[str, str | bool]:
    """Toggle an emoji reaction on a queue item."""
    try:
        active = await service.toggle_reaction(
            reaction_data.item_id,
            reaction_data.user_id,
            reaction_data.reaction,
        )
        return {
            "item_id": reaction_data.item_id,
            "user_id": reaction_data.user_id,
            "reaction": reaction_data.reaction,
            "active": active,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/reactions/room/{room_id}")
async def get_room_reactions(
    room_id: str,
    service: ReactionService = Depends(get_reaction_service),
) -> dict[str, dict[str, list[str]]]:
    """Get all reactions for all queue items in a room."""
    return await service.get_room_reactions(room_id)


@router.post("/history/{history_id}/rate", response_model=WatchHistory)
async def rate_watched_item(
    history_id: str,
    rating_data: RatingUpdate,
    service: HistoryService = Depends(get_history_service),
) -> WatchHistory:
    """Add or update a user's rating for a watched item.

    Rating must be 1-5 stars.
    """
    try:
        history = await service.add_rating(
            history_id,
            rating_data.user_id,
            rating_data.rating,
        )
        if not history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="History entry not found",
            )
        return history
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/history/room/{room_id}", response_model=list[WatchHistory])
async def get_room_history(
    room_id: str,
    limit: int = 50,
    skip: int = 0,
    service: HistoryService = Depends(get_history_service),
) -> list[WatchHistory]:
    """Get watch history for a room."""
    return await service.get_room_history(room_id, limit=limit, skip=skip)


@router.get("/history/room/{room_id}/stats")
async def get_history_stats(
    room_id: str,
    service: HistoryService = Depends(get_history_service),
) -> dict:
    """Get watch statistics for a room."""
    return await service.get_stats(room_id)
