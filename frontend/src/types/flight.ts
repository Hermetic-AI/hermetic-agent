export interface Flight {
  id: string;
  airline: string;
  airlineCode: string;
  flightNumber: string;
  departure: {
    city: string;
    airport: string;
    airportCode: string;
    time: string;
    date: string;
  };
  arrival: {
    city: string;
    airport: string;
    airportCode: string;
    time: string;
    date: string;
  };
  duration: string;
  cabinClass: 'economy' | 'business' | 'first';
  price: number;
  tax: number;
  remainingSeats: number;
  aircraft: string;
}

export interface FlightSearchParams {
  departureCity: string;
  arrivalCity: string;
  departureDate: string;
  returnDate?: string;
  cabinClass?: 'economy' | 'business' | 'first';
  passengers: number;
}

export interface FlightSearchResult {
  outboundFlights: Flight[];
  returnFlights?: Flight[];
  isRoundTrip: boolean;
}
