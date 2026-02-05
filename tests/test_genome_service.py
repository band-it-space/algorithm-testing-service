import pytest
from app.models.algorithm_models import AlgorithmParameters, ParameterRange
from app.services.genome_service import (
    parse_parameter_ranges,
    generate_genomes,
    calculate_total_combinations,
    get_genome_by_id,
    get_variable_parameter_names,
)


class TestParameterRange:
    """Tests for ParameterRange model."""
    
    def test_generate_values_with_change(self):
        """Test generating values when change=True."""
        param_range = ParameterRange(
            name="input_B1_upper_range",
            base=0.65,
            min_val=0.55,
            max_val=0.75,
            step=0.1,
            change=True
        )
        
        values = param_range.generate_values()
        
        assert len(values) == 3
        assert 0.55 in values
        assert 0.65 in values
        assert 0.75 in values
    
    def test_generate_values_without_change(self):
        """Test generating values when change=False."""
        param_range = ParameterRange(
            name="input_B1_lookback",
            base=20,
            min_val=1,
            max_val=1,
            step=1,
            change=False
        )
        
        values = param_range.generate_values()
        
        assert len(values) == 1
        assert values[0] == 20
    
    def test_from_dict(self):
        """Test creating ParameterRange from dict."""
        data = {
            "Parameter Variable": "input_B1_upper_range",
            "Base": 0.65,
            "Min": 0.55,
            "Max": 0.75,
            "Step": 0.1,
            "Change": "TRUE",
            "Rule": "B1"
        }
        
        param_range = ParameterRange.from_dict(data)
        
        assert param_range.name == "input_B1_upper_range"
        assert param_range.base == 0.65
        assert param_range.change is True


class TestGenomeService:
    """Tests for genome generation service."""
    
    @pytest.fixture
    def sample_ranges_data(self):
        """Sample parameter ranges matching Input Sample CSV."""
        return [
            {"Parameter Variable": "input_B1_upper_range", "Base": 0.65, "Min": 0.55, "Max": 0.75, "Step": 0.1, "Change": "TRUE", "Rule": "B1"},
            {"Parameter Variable": "input_B3_LR_lookback", "Base": 58, "Min": 40, "Max": 80, "Step": 10, "Change": "TRUE", "Rule": "B3"},
            {"Parameter Variable": "input_B11_atr_threshold", "Base": 0.87, "Min": 0.75, "Max": 0.95, "Step": 0.05, "Change": "TRUE", "Rule": "B11"},
            {"Parameter Variable": "input_B1_lookback", "Base": 20, "Min": 1, "Max": 1, "Step": 1, "Change": "FALSE", "Rule": "B1"},
        ]
    
    def test_parse_parameter_ranges(self, sample_ranges_data):
        """Test parsing parameter ranges from dict list."""
        ranges = parse_parameter_ranges(sample_ranges_data)
        
        assert len(ranges) == 4
        assert ranges[0].name == "input_B1_upper_range"
        assert ranges[0].change is True
    
    def test_calculate_total_combinations(self, sample_ranges_data):
        """Test calculating total combinations."""
        ranges = parse_parameter_ranges(sample_ranges_data)
        total = calculate_total_combinations(ranges)
        
        # 3 × 5 × 5 + 1 (BASE) = 76
        assert total == 76
    
    def test_generate_genomes_base_is_g000(self, sample_ranges_data):
        """Test that BASE genome is G_000."""
        ranges = parse_parameter_ranges(sample_ranges_data)
        genomes = generate_genomes(ranges)
        
        assert genomes[0]["genome_id"] == "G_000"
        assert genomes[0]["is_base"] is True
    
    def test_generate_genomes_count(self, sample_ranges_data):
        """Test correct number of genomes generated."""
        ranges = parse_parameter_ranges(sample_ranges_data)
        genomes = generate_genomes(ranges)
        
        expected = calculate_total_combinations(ranges)
        assert len(genomes) == expected
    
    def test_get_genome_by_id(self, sample_ranges_data):
        """Test retrieving genome by ID."""
        ranges = parse_parameter_ranges(sample_ranges_data)
        genomes = generate_genomes(ranges)
        
        base = get_genome_by_id(genomes, "G_000")
        assert base is not None
        assert base["is_base"] is True
        
        g001 = get_genome_by_id(genomes, "G_001")
        assert g001 is not None
        assert g001["is_base"] is False
        
        missing = get_genome_by_id(genomes, "G_999999")
        assert missing is None
    
    def test_get_variable_parameter_names(self, sample_ranges_data):
        """Test getting list of variable parameters."""
        ranges = parse_parameter_ranges(sample_ranges_data)
        names = get_variable_parameter_names(ranges)
        
        assert "input_B1_upper_range" in names
        assert "input_B3_LR_lookback" in names
        assert "input_B11_atr_threshold" in names
        assert "input_B1_lookback" not in names  # change=False


class TestAlgorithmParameters:
    """Tests for AlgorithmParameters model."""
    
    def test_default_values(self):
        """Test that defaults match base values."""
        params = AlgorithmParameters()
        
        assert params.input_B1_lookback == 20
        assert params.input_B1_upper_range == 0.65
        assert params.input_S1_atr_mult == 3.7
    
    def test_to_dict(self):
        """Test serialization to dict."""
        params = AlgorithmParameters()
        d = params.to_dict()
        
        assert isinstance(d, dict)
        assert "input_B1_lookback" in d
        assert d["input_B1_lookback"] == 20
    
    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "input_B1_upper_range": 0.75,
            "input_B3_LR_lookback": 40,
            "unknown_param": 999  # Should be ignored
        }
        
        params = AlgorithmParameters.from_dict(data)
        
        assert params.input_B1_upper_range == 0.75
        assert params.input_B3_LR_lookback == 40
        assert params.input_B1_lookback == 20  # Default value
    
    def test_from_empty_dict(self):
        """Test creating from empty dict uses defaults."""
        params = AlgorithmParameters.from_dict({})
        
        assert params.input_B1_lookback == 20
        assert params.input_B1_upper_range == 0.65
