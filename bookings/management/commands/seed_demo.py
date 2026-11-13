from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from bookings.models import Event, Room, VenueSpace, ContactInquiry, ContactMessage


class Command(BaseCommand):
    help = "Add rich, realistic Navratri, luxury stays, party plots, and wedding banquet halls for Amazing Ahmedabad."

    def handle(self, *args, **options):
        start = timezone.localtime(timezone.now()).replace(hour=19, minute=0, second=0, microsecond=0)

        # 1. EXPANDED EVENTS & NAVRATRI SLOTS
        event_data = [
            (
                "Riverfront Maha Garba Mahotsav", "Navratri",
                "Ahmedabad's most iconic riverside Garba night featuring legendary folk artists, live dhol beats, authentic Gujarati food street, and an expansive 50,000 sq ft dance floor.",
                "Riverfront Event Grounds", 799, 350, 2,
                "Entry pass, access to main garba circle, traditional drinking water, and parking coupon.",
                "Traditional attire required (Chaniya Choli / Kurta Pyjama). Entry permitted till 10:30 PM. Valid photo ID required.",
                "photo-1506157786151-b8491531f063"
            ),
            (
                "SBR VIP Dandiya Utsav - Premium Pass", "Navratri",
                "An exclusive, high-energy dandiya night on Sindhu Bhavan Road with celebrity performers, air-cooled lounges, dedicated food village, and wooden spring dance floor.",
                "Sindhu Bhavan Cultural Grounds", 1299, 180, 4,
                "VIP fast-track entry, wooden spring dance floor access, a pair of wooden dandiya sticks, and complimentary mocktail.",
                "Couple and family friendly. Shoes must be removed before entering the wooden dance floor. No outside food permitted.",
                "photo-1492684223066-81342ee5ff30"
            ),
            (
                "Heritage Pol Sheri Garba - Old City", "Navratri",
                "Experience the 600-year-old traditional Sheri Garba inside Ahmedabad's UNESCO World Heritage pol. Acoustic live folk instruments, clay lamps (garbi), and historic ambiance.",
                "Dhal ni Pol Heritage Courtyard", 499, 90, 6,
                "Historic courtyard access, live Gujarati folk singing, prasad box, and guided heritage walk before garba.",
                "Strictly traditional Indian ethnic wear. Respect local residents and historic pol guidelines. Photography without flash.",
                "photo-1514525253161-7a46d19cd819"
            ),
            (
                "GMDC Grand Star Garba Night", "Navratri",
                "Mega celebration at GMDC Ground with laser light spectacle, synchronized folk choreography, famous playback singers, and VIP corporate boxes.",
                "GMDC Mega Arena, Drive-In", 899, 250, 8,
                "General arena entry, security wristband, festival sticker, and food court entry.",
                "All age groups welcome. Gates open at 7:00 PM. Re-entry not allowed once barcode is scanned.",
                "photo-1516450360452-9312f5e86fc7"
            ),
            (
                "Bopal United Dandiya Night", "Navratri",
                "A community favorite open-air dandiya celebration in South Bopal with live orchestra, kids play zone, and delicious Kathiyawadi food stalls.",
                "South Bopal Open Grounds", 449, 120, 10,
                "Garba and dandiya access, kids entertainment zone access, and mineral water.",
                "Children under 5 free with valid age proof. Traditional attire encouraged.",
                "photo-1504609813442-a8924e83f76e"
            ),
            (
                "Midnight Bollywood DJ Bash", "Party",
                "Dance to chart-topping Bollywood and Punjabi remixes with Ahmedabad's top DJs, LED stage, confetti cannons, and midnight snack counters.",
                "Prahlad Nagar Sky Lounge", 1199, 80, 12,
                "Club floor access, 1 welcome festive mocktail, and DJ floor pass.",
                "Age limit 18+. Physical photo ID required. Dress code: Smart casual or party festive.",
                "photo-1470229722913-7c0e2dbbafd3"
            ),
            (
                "Acoustic Rooftop Sessions", "Live music",
                "An intimate sunset musical evening featuring soulful Gujarati and Hindi singer-songwriters under the stars on a terrace with city panoramic views.",
                "Satellite Terrace Garden", 599, 65, 14,
                "Reserved amphitheater seating, welcome specialty coffee, and acoustic concert access.",
                "Seating on first-come basis within reserved zone. Quiet listening room etiquette requested.",
                "photo-1508700115892-45ecd05ae2ad"
            ),
            (
                "Sufi Courtyard Gala", "Live music",
                "A mystical evening of traditional Qawwali and Sufi compositions by renowned folk masters in a serene heritage garden courtyard.",
                "Bopal Heritage Courtyard", 999, 75, 16,
                "Reserved baithak cushion seating, Kashmiri kahwa welcome tea, and artist interaction.",
                "Gates open 30 minutes before performance. Mobile phones on silent mode during recital.",
                "photo-1459749411175-04bf5292ceea"
            ),
            (
                "Sunday Gujarati Food &amp; Folk Fest", "Festival",
                "Day-long celebration with 40+ authentic street food stalls, live puppet shows, folk dance workshops, handloom stalls, and evening garba tutorial.",
                "Kankaria Lakefront Grounds", 349, 300, 18,
                "Festival entrance, all cultural stage performances, and access to kids craft workshop.",
                "Food stalls accept UPI/Cash directly. Entry tickets valid for full day from 11 AM to 9 PM.",
                "photo-1492684223066-81342ee5ff30"
            ),
            (
                "Royal Rajwada Sangeet &amp; Garba", "Navratri",
                "A royal palace themed garba night with grand royal entry, live shehnai and nagada troupes, and royal photo booths in SG Highway.",
                "SG Highway Palace Grounds", 999, 160, 20,
                "Royal red carpet entry, dandiya sticks pair, and complimentary festive sweet box.",
                "Strict dress code: Royal ethnic attire. Family and couples only.",
                "photo-1506157786151-b8491531f063"
            ),
        ]

        for name, category, description, venue, price, tickets, day_offset, included, rules, photo in event_data:
            event_start = start + timedelta(days=day_offset)
            event, _ = Event.objects.update_or_create(
                name=name,
                defaults={
                    "category": category,
                    "description": description,
                    "venue": venue,
                    "city": "Ahmedabad",
                    "address": f"{venue}, Ahmedabad",
                    "organizer_name": "Amazing Ahmedabad Celebrations",
                    "starts_at": event_start,
                    "ends_at": event_start + timedelta(hours=4),
                    "ticket_price": Decimal(str(price)),
                    "tickets_available": tickets,
                    "age_limit": "All ages" if "Family" in name or "Heritage" in name else "18+" if "DJ" in name else "All ages",
                    "what_is_included": included,
                    "entry_rules": rules,
                    "is_published": True,
                    "cover_image_url": f"https://images.unsplash.com/{photo}?auto=format&fit=crop&w=1200&q=85",
                }
            )

        # 2. LUXURY HOTEL ROOMS & SUITES
        room_data = [
            (
                "The Heritage Haveli Royal Suite",
                "An opulent suite carved in traditional Gujarati teakwood with a private courtyard view, handcrafted jhula (swing), marble bathroom with deep soaking tub, and regal antique furnishings.",
                5800, 2, "King four-poster bed",
                "High-speed Wi-Fi, Central AC, Deep soaking jacuzzi tub, Private heritage balcony, In-room espresso machine, Breakfast included, 24/7 Butler on call",
                True, "Navrangpura, Ahmedabad",
                "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&w=1200&q=82",
                Decimal("4.9"), "Heritage Haveli Stay"
            ),
            (
                "Presidential Palace Suite - SG Highway",
                "A luxurious 950 sq ft top-floor suite featuring panoramic skyline views of SG Highway, separate living salon, dining area, luxury bath amenities, and complimentary cocktail hours.",
                8500, 4, "Grand King bed + sofa bed",
                "High-speed Wi-Fi, Dual-zone AC, 65-inch Smart TV, Executive lounge access, Valet parking, Chef curated breakfast, Late check-out till 2 PM",
                True, "SG Highway, Ahmedabad",
                "https://images.unsplash.com/photo-1590490360182-c33d57733427?auto=format&fit=crop&w=1200&q=82",
                Decimal("4.9"), "The Grand Ahmedabad Hotel"
            ),
            (
                "Executive Business Suite - Prahlad Nagar",
                "Designed for premium travelers and event attendees with ergonomic workspace, high-speed fiber internet, rainfall shower, and seamless connectivity to corporate hubs.",
                4600, 2, "King bed",
                "Wi-Fi, Silent inverter AC, Work desk & ergonomic chair, Mini bar, Smart TV, Free breakfast buffet, Gym & pool access",
                True, "Prahlad Nagar, Ahmedabad",
                "https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=1200&q=82",
                Decimal("4.8"), "Prahlad Nagar Executive Hotel"
            ),
            (
                "Lush Garden Villa Room - Sindhu Bhavan",
                "Ground-floor boutique room opening directly onto private manicured lawns on Sindhu Bhavan Road. Peace and luxury within walking distance of top nightlife.",
                4900, 3, "King bed + rollaway bed",
                "Private garden patio, Wi-Fi, Climate control AC, Luxury organic toiletries, Welcome fruit basket, Gourmet breakfast",
                True, "Sindhu Bhavan Road, Ahmedabad",
                "https://images.unsplash.com/photo-1566665797739-1674de7a421a?auto=format&fit=crop&w=1200&q=82",
                Decimal("4.8"), "Sindhu Bhavan Boutique Stays"
            ),
            (
                "City Comfort Deluxe Room",
                "A stylish, air-conditioned room tailored for festival attendees wanting modern comfort, spotlessly clean bedding, and quick transit to city garba venues.",
                2400, 2, "Queen bed",
                "Wi-Fi, Air conditioning, 43-inch Smart TV, Tea/coffee maker, Private bathroom with hot shower, Free parking",
                False, "Navrangpura, Ahmedabad",
                "https://images.unsplash.com/photo-1591088398332-8a7791972843?auto=format&fit=crop&w=1200&q=82",
                Decimal("4.6"), "City Comfort Inn"
            ),
            (
                "Family Grand Suite - Vastrapur",
                "Spacious multi-room suite ideal for families attending weddings or Navratri festivals. Features two interconnected bedrooms and a cozy family lounge.",
                4200, 4, "1 King bed + 2 Twin beds",
                "Wi-Fi, Individual AC in all rooms, Living lounge with sofa, Refrigerator, Microwave, Breakfast buffet, Kids play area access",
                True, "Vastrapur, Ahmedabad",
                "https://images.unsplash.com/photo-1578683010236-d716f9a3f461?auto=format&fit=crop&w=1200&q=82",
                Decimal("4.7"), "Vastrapur Family Suites"
            ),
        ]

        for name, desc, price, cap, bed, amen, bf, addr, photo, rating, prop_name in room_data:
            room_type = "Presidential suite" if "Presidential" in name else "Royal suite" if "Royal" in name else "Family suite" if "Family" in name else "Executive suite" if "Executive" in name else "Deluxe room"
            Room.objects.update_or_create(
                name=name,
                defaults={
                    "property_name": prop_name,
                    "room_type": room_type,
                    "description": desc,
                    "city": "Ahmedabad",
                    "address": addr,
                    "price_per_night": Decimal(str(price)),
                    "capacity": cap,
                    "bed_type": bed,
                    "amenities": amen,
                    "breakfast_included": bf,
                    "cover_image_url": photo,
                    "guest_rating": rating,
                    "cancellation_policy": "Free cancellation up to 24 hours before check-in. Instant refund or credit.",
                    "house_rules": "Government issued photo ID required at check-in. Standard check-in 2:00 PM, check-out 11:00 AM.",
                    "is_available": True,
                }
            )

        # 3. PARTY PLOTS & HOURLY CELEBRATION LAWNS
        plot_data = [
            (
                "Shreeji Celebration Lawn - Bopal",
                "Spacious open-air natural grass plot surrounded by lush palm trees in Bopal. Designed for 1–6 hour birthday parties, engagement ceremonies, and private family get-togethers.",
                "Bopal, Ahmedabad", 6500, 250,
                "Natural lawn turf, Decorative festoon lighting, Sound system stage, 2 AC green rooms, 80-car parking space, 30KW power backup",
                "photo-1519167758481-83f550bb49b3"
            ),
            (
                "The Grand Meadows - Sindhu Bhavan Road",
                "Ahmedabad's most prestigious luxury party lawn located right on Sindhu Bhavan Road. Ideal for upscale sangeet nights, ring ceremonies, and milestone corporate bashes.",
                "Sindhu Bhavan Road, Ahmedabad", 11500, 500,
                "Bermuda grass lawn, Moving head LED stage lights, VIP lounge cabanas, Valet parking for 150 vehicles, Bridal dressing suite, Full generator backup",
                "photo-1511795409834-ef04bbd61622"
            ),
            (
                "Aura Green Party Plot - SG Highway",
                "Expansive 25,000 sq ft celebration lawn with landscaped perimeter, elevated performance stage, modern food stall gazebos, and hassle-free highway connectivity.",
                "SG Highway, Ahmedabad", 9500, 450,
                "Lawn area, Built-in stage, Designer lighting arches, Separate catering prep zone, Valet parking, Security guards on site",
                "photo-1519225421980-715cb0215aed"
            ),
            (
                "Royal Palm Celebration Lawn - Thaltej",
                "Serene, private garden venue nestled in Thaltej with illuminated palm trees, acoustic layout, and romantic ambiance for evening gatherings and anniversaries.",
                "Thaltej, Ahmedabad", 7800, 350,
                "Lush green carpet lawn, Acoustic layout, Ambient fairy lighting, 2 Changing rooms, Guest parking area, Drinking water setup",
                "photo-1464366400600-7168b8af9bc3"
            ),
            (
                "Vrindavan Open Lawn - Chandkheda",
                "Affordable and versatile hourly lawn in Chandkheda with open layout, children's play area, and flexible decoration options for birthdays and family functions.",
                "Chandkheda, Ahmedabad", 5500, 300,
                "Open lawn, Standard stage, Decorative lights, Parking area, Power points for catering, On-site venue manager",
                "photo-1519167758481-83f550bb49b3"
            ),
        ]

        for name, desc, addr, rate, cap, amen, photo in plot_data:
            VenueSpace.objects.update_or_create(
                name=name,
                defaults={
                    "space_type": VenueSpace.PARTY_PLOT,
                    "description": desc,
                    "city": "Ahmedabad",
                    "address": addr,
                    "hourly_rate": Decimal(str(rate)),
                    "capacity": cap,
                    "amenities": amen,
                    "rules": "1–6 hour bookings available. Music allowed till 10:00 PM per city noise regulations. Outside catering permitted with prior notice.",
                    "cover_image_url": f"https://images.unsplash.com/{photo}?auto=format&fit=crop&w=1200&q=82",
                    "is_available": True,
                }
            )

        # 4. WEDDING & BANQUET HALLS
        hall_data = [
            (
                "The Rajwada Palace Banquet - SG Highway",
                "A royal palace themed grand banquet hall with soaring ceilings, handcrafted Belgian crystal chandeliers, dedicated dining arena, and capacity for grand royal weddings.",
                "SG Highway, Ahmedabad", 28000, 1200,
                "Full Central AC, 40 ft elevated royal stage, Separate 500-seat dining hall, 2 Luxury bridal suites with salon mirrors, 250-car valet parking, Professional sound & light rig",
                "photo-1519225421980-715cb0215aed"
            ),
            (
                "Shahi Darbar Grand Ballroom - Satellite",
                "Centrally air-conditioned pillarless ballroom in Satellite featuring acoustic walls, mood lighting, and modern banquet layout for weddings, receptions, and sangeet functions.",
                "Satellite, Ahmedabad", 19500, 750,
                "Pillarless AC ballroom, High-definition LED backdrop screen, Pre-function cocktail area, Groom and bridal green rooms, Dedicated kitchen prep zone, Valet parking",
                "photo-1464366400600-7168b8af9bc3"
            ),
            (
                "The Imperial Wedding Hall - Bodakdev",
                "Contemporary luxury banquet hall in Bodakdev with Italian marble flooring, designer false ceiling, VIP lounge, and complete event infrastructure.",
                "Bodakdev, Ahmedabad", 24000, 900,
                "Central AC, Grand entrance foyer, Stage lighting system, VIP holding room, Modern washrooms, 150-car covered parking",
                "photo-1511795409834-ef04bbd61622"
            ),
            (
                "Shehnai Celebration Hall - Sindhu Bhavan",
                "A vibrant, stylish banquet space on Sindhu Bhavan Road ideal for wedding ceremonies, engagement parties, and grand multi-course banquets.",
                "Sindhu Bhavan Road, Ahmedabad", 22000, 800,
                "Central AC, Ambient ceiling lights, Bridal suite with private bath, Sound system, Elevator access, Valet parking",
                "photo-1519167758481-83f550bb49b3"
            ),
        ]

        for name, desc, addr, rate, cap, amen, photo in hall_data:
            VenueSpace.objects.update_or_create(
                name=name,
                defaults={
                    "space_type": VenueSpace.BANQUET_HALL,
                    "description": desc,
                    "city": "Ahmedabad",
                    "address": addr,
                    "hourly_rate": Decimal(str(rate)),
                    "capacity": cap,
                    "amenities": amen,
                    "rules": "2–12 hour bookings supported. Setup and teardown must fit within reserved slot hours. Security deposit collected at check-in.",
                    "cover_image_url": f"https://images.unsplash.com/{photo}?auto=format&fit=crop&w=1200&q=82",
                    "is_available": True,
                }
            )

        # 5. SAMPLE INQUIRIES FOR THE ADMIN INBOX
        sample_inquiries = [
            (
                "Harshil Mehta", "harshil@example.com", "+919825012345", "venue",
                "Party Plot Booking Inquiry for Engagement",
                "Hello Amazing Ahmedabad team! We are looking to book Shreeji Celebration Lawn in Bopal for an engagement gathering of around 200 guests next month. Can we bring our own Maharaj for Gujarati catering?",
                "new"
            ),
            (
                "Pooja Trivedi", "pooja.t@example.com", "+919879123456", "booking",
                "Bulk VIP Navratri Garba Passes Inquiry",
                "Hi, we need 25 VIP passes for the SBR VIP Dandiya Utsav for our corporate team. Do you offer group discounts or a dedicated VIP lounge for corporate bookings?",
                "in_progress"
            ),
            (
                "Kunal Shah", "kunal.shah@example.com", "+919898011223", "venue",
                "Wedding Date Availability at Rajwada Palace",
                "Looking to book the Rajwada Palace Banquet on SG Highway for an evening wedding reception from 5 PM to 11 PM (6 hours). Please confirm decoration guidelines and generator power.",
                "resolved"
            ),
            (
                "Ritu Parekh", "ritu.parekh@example.com", "+919909022334", "stay",
                "Haveli Suite Extended Stay Booking",
                "We want to book The Heritage Haveli Royal Suite for 4 nights during Navratri. Is airport pick-up and drop available from Sardar Vallabhbhai Patel International Airport?",
                "new"
            ),
        ]

        for name, email, phone, topic, subject, msg, status in sample_inquiries:
            inquiry, created = ContactInquiry.objects.get_or_create(
                email=email, subject=subject,
                defaults={
                    "name": name,
                    "phone": phone,
                    "topic": topic,
                    "message": msg,
                    "status": status,
                }
            )
            if created:
                ContactMessage.objects.create(
                    inquiry=inquiry,
                    author_name=name,
                    body=msg,
                )

        # 5. FOOD HUB ITEMS
        from bookings.models import FoodItem
        from django.core.management import call_command
        from pathlib import Path

        if FoodItem.objects.count() == 0:
            fixture_path = Path(__file__).resolve().parent.parent.parent / "fixtures" / "initial_catalog.json"
            if fixture_path.exists():
                call_command("loaddata", str(fixture_path), verbosity=1)
                self.stdout.write(self.style.SUCCESS("Loaded 109 Amdavad Food Hub dishes from catalog fixture!"))

        self.stdout.write(self.style.SUCCESS("Successfully seeded rich Navratri passes, luxury rooms, party plots, wedding halls, and support inquiries for Amazing Ahmedabad!"))
