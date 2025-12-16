from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

class Contact(BaseModel):
    id: Optional[int] = None
    name: str
    phone: str

contacts: List[Contact] = []
next_id = 1

@app.post("/contacts/", response_model=Contact)
def create_contact(contact: Contact):
    global next_id
    contact.id = next_id
    next_id += 1
    contacts.append(contact)
    return contact

@app.get("/contacts/", response_model=List[Contact])
def read_contacts():
    return contacts

@app.get("/contacts/{contact_id}", response_model=Contact)
def read_contact(contact_id: int):
    for contact in contacts:
        if contact.id == contact_id:
            return contact
    raise HTTPException(status_code=404, detail="Contact not found")

@app.put("/contacts/{contact_id}", response_model=Contact)
def update_contact(contact_id: int, updated_contact: Contact):
    for i, contact in enumerate(contacts):
        if contact.id == contact_id:
            updated_contact.id = contact_id
            contacts[i] = updated_contact
            return updated_contact
    raise HTTPException(status_code=404, detail="Contact not found")

@app.delete("/contacts/{contact_id}", response_model=Contact)
def delete_contact(contact_id: int):
    for i, contact in enumerate(contacts):
        if contact.id == contact_id:
            return contacts.pop(i)
    raise HTTPException(status_code=404, detail="Contact not found")
