import axios from "axios";

const http = axios.create({
  timeout: 8000,
});

export default http;
