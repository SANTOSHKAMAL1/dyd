"""
Script to create an admin user in Neo4j database
Run this once to create your admin account
"""

from werkzeug.security import generate_password_hash
from utils_def_1 import driver, NEO4J_DATABASE

def create_admin_user():
    """Create an admin user in the database"""
    
    # Admin credentials - CHANGE THESE!
    admin_username = "admin"
    admin_password = "admin123"  # Change this to a secure password
    admin_email = "admin@jainuniversity.edu"
    
    if not driver:
        print("❌ Error: Database connection failed!")
        return False
    
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            # Check if admin already exists
            exists = s.run("""
                MATCH (u:User {username: $username}) 
                RETURN u
            """, username=admin_username).single()
            
            if exists:
                # Update existing user to admin
                s.run("""
                    MATCH (u:User {username: $username})
                    SET u.is_admin = true
                """, username=admin_username)
                print(f"✅ Updated existing user '{admin_username}' to admin!")
            else:
                # Create new admin user
                hashed_password = generate_password_hash(admin_password)
                
                s.run("""
                    CREATE (u:User {
                        username: $username,
                        password: $password,
                        email: $email,
                        display_name: 'Administrator',
                        is_admin: true,
                        created_at: datetime(),
                        marks_completed: true,
                        riasec_completed: true,
                        bio: 'System Administrator',
                        location: 'Jain University',
                        phone: ''
                    })
                """, 
                username=admin_username,
                password=hashed_password,
                email=admin_email)
                
                print(f"✅ Admin user created successfully!")
                print(f"   Username: {admin_username}")
                print(f"   Password: {admin_password}")
                print(f"   ⚠️  CHANGE THE PASSWORD AFTER FIRST LOGIN!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating admin user: {str(e)}")
        return False

def make_user_admin(username):
    """Make an existing user an admin"""
    if not driver:
        print("❌ Error: Database connection failed!")
        return False
    
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})
                SET u.is_admin = true
                RETURN u.username as username
            """, username=username).single()
            
            if result:
                print(f"✅ User '{username}' is now an admin!")
                return True
            else:
                print(f"❌ User '{username}' not found!")
                return False
                
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def remove_admin_access(username):
    """Remove admin access from a user"""
    if not driver:
        print("❌ Error: Database connection failed!")
        return False
    
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})
                SET u.is_admin = false
                RETURN u.username as username
            """, username=username).single()
            
            if result:
                print(f"✅ Admin access removed from '{username}'!")
                return True
            else:
                print(f"❌ User '{username}' not found!")
                return False
                
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def list_all_admins():
    """List all admin users"""
    if not driver:
        print("❌ Error: Database connection failed!")
        return
    
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            admins = s.run("""
                MATCH (u:User)
                WHERE u.is_admin = true
                RETURN u.username as username, u.email as email
                ORDER BY u.username
            """).data()
            
            if admins:
                print("\n👥 Admin Users:")
                print("-" * 50)
                for admin in admins:
                    print(f"   Username: {admin['username']}")
                    print(f"   Email: {admin['email']}")
                    print("-" * 50)
            else:
                print("❌ No admin users found!")
                
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("   Jain University - Admin User Management")
    print("="*60 + "\n")
    
    print("Options:")
    print("1. Create new admin user")
    print("2. Make existing user admin")
    print("3. Remove admin access")
    print("4. List all admins")
    print("5. Exit")
    
    choice = input("\nEnter your choice (1-5): ").strip()
    
    if choice == "1":
        create_admin_user()
    elif choice == "2":
        username = input("Enter username to make admin: ").strip()
        make_user_admin(username)
    elif choice == "3":
        username = input("Enter username to remove admin access: ").strip()
        remove_admin_access(username)
    elif choice == "4":
        list_all_admins()
    elif choice == "5":
        print("Goodbye!")
    else:
        print("❌ Invalid choice!")
    
    print("\n" + "="*60 + "\n")