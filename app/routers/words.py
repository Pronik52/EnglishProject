from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas, models
from ..crud import words as crud_words
from ..auth import get_current_user

router = APIRouter(prefix="/words", tags=["words"])


@router.post("", response_model=schemas.WordResponse)
def create_word(
    word: schemas.WordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return crud_words.create_word(db, word=word, owner_id=current_user.id)


@router.get("", response_model=list[schemas.WordResponse])
def read_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return crud_words.get_words_by_owner(db, owner_id=current_user.id)


@router.get("/{word_id}", response_model=schemas.WordResponse)
def read_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.get_word(db, word_id=word_id, owner_id=current_user.id)
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word


@router.delete("/{word_id}")
def remove_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ok = crud_words.delete_word(db, word_id=word_id, owner_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return {"detail": "Слово удалено"}