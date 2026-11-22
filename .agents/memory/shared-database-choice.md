---
name: Shared database choice
description: Owner's database-sharing scope and prohibition on substituting copies.
---

Właścicielka świadomie wybrała jedną obecną bazę PostgreSQL dla development
i opublikowanej aplikacji MCOD, zamiast kopiowania danych do odrębnej bazy.
Nie zastępować tego wyboru kopią ani pustą bazą; nie nadpisywać ręcznie
zarządzanego połączenia i nie obchodzić ograniczeń platformy.

**Why:** Właścicielka wymaga zachowania istniejących danych i jednej bazy,
a w przypadku braku obsługi — jawnego zgłoszenia ograniczenia, nie pozornej realizacji.

**How to apply:** Najpierw sprawdzić bieżące możliwości platformy w oficjalnych
źródłach. Nazwa `DATABASE_URL` i opcja kopiowania danych w Publishing nie dowodzą
połączenia z tą samą fizyczną bazą. Zmiana na odrębne bazy wymaga nowej decyzji
właścicielki.
