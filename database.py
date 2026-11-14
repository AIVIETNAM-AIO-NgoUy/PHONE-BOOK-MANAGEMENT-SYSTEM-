import psycopg2

def init_database():
    conn = psycopg2.connect(
        host="localhost",
        database="phone_book_db",
        user="postgres",
        password="your_password",
        port="5432"
    )
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "User" (
            UserID VARCHAR(10) PRIMARY KEY,
            userName VARCHAR(50) NOT NULL,
            passwordHash VARCHAR(255) NOT NULL,
            fullName VARCHAR(100),
            email VARCHAR(100),
            avatarURL VARCHAR(255),
            role VARCHAR(20),
            accountStatus VARCHAR(20)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "ContacBook" (
            bookID VARCHAR(10) PRIMARY KEY,
            userID VARCHAR(10),
            createdDate DATE,
            FOREIGN KEY (userID) REFERENCES "User"(UserID) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "Contact" (
            contactID VARCHAR(10) PRIMARY KEY,
            bookID VARCHAR(10),
            fullName VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            address VARCHAR(255),
            workAddress VARCHAR(255),
            avatar VARCHAR(255),
            birthday DATE,
            notes TEXT,
            FOREIGN KEY (bookID) REFERENCES "ContacBook"(bookID) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "PhoneNumber" (
            phoneID VARCHAR(10) PRIMARY KEY,
            contactID VARCHAR(10),
            phoneNumber VARCHAR(20) NOT NULL,
            type VARCHAR(20),
            isPrimary BOOLEAN,
            FOREIGN KEY (contactID) REFERENCES "Contact"(contactID) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "GroupTable" (
            groupID VARCHAR(10) PRIMARY KEY,
            bookID VARCHAR(10),
            groupName VARCHAR(100) NOT NULL,
            description TEXT,
            FOREIGN KEY (bookID) REFERENCES "ContacBook"(bookID) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "ContactGroup" (
            contactID VARCHAR(10),
            groupID VARCHAR(10),
            PRIMARY KEY (contactID, groupID),
            FOREIGN KEY (contactID) REFERENCES "Contact"(contactID) ON DELETE CASCADE,
            FOREIGN KEY (groupID) REFERENCES "GroupTable"(groupID) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "FavoriteList" (
            favoriteListID VARCHAR(10) PRIMARY KEY,
            bookID VARCHAR(10),
            FOREIGN KEY (bookID) REFERENCES "ContacBook"(bookID) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "FavoriteItem" (
            favoriteItemID VARCHAR(10) PRIMARY KEY,
            favoriteListID VARCHAR(10),
            contactID VARCHAR(10),
            priority INTEGER,
            addedDate DATE,
            FOREIGN KEY (favoriteListID) REFERENCES "FavoriteList"(favoriteListID) ON DELETE CASCADE,
            FOREIGN KEY (contactID) REFERENCES "Contact"(contactID) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_database()